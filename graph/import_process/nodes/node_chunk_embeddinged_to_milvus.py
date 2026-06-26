import os
import sys

from pymilvus import DataType, MilvusClient

from conf.milvus_config import milvus_config
from conf.embedding_config import embedding_config
from core.logger import logger
from graph.import_process.state import ImportGraphState, create_default_state
from clients.milvus_client import get_milvus_client
from utils.task_util import add_running_task
from utils.utils import escape_milvus_string

"""
 该节点是将切分好并向量化的chunks，存入milvus数据库中，步骤有
 1.提取state中的要用到的参数chunks,并做校验,校验每个dict是不是都有向量字段
 2.准备好milvus的连接,准备好要插入milvus的collection,没有就创建，
    然后根据chunk结构添加列,有primary_key(自生成变chunk_id)
 3.判collection下有没有同名的item_name，有就删除，保证数据是最新的
 4.插入数据
"""

_model_vector_dimension = embedding_config.model_vector_dimension


def step1_validate_params(state) -> list:
    chunk = state.get("chunks", [])

    if not chunk:
        logger.error("没有切分好的chunk数据")
        raise RuntimeError("没有切分好的chunk数据")

    dense_vector = [chunk_item.get("dense") for chunk_item in chunk]
    sparse_vector = [chunk_item.get("sparse") for chunk_item in chunk]
    print(dense_vector, sparse_vector)
    if not all(dense_vector) or not all(sparse_vector):
        logger.error("向量数据不完整，请检查上游节点数据")
        raise RuntimeError("向量数据不完整，请检查上游节点数据")

    return chunk


def step2_prepare_milvus_connection(collection_name: str,
                                    model_vector_dimension: int = _model_vector_dimension):
    milvus_client = get_milvus_client()
    if not milvus_client:
        raise RuntimeError("Milvus连接失败")

    # 列出所有集合
    # collections = milvus_client.list_collections()

    if not milvus_client.has_collection(collection_name):
        # 没有就创建集合
        logger.info(f"未查询到集合{collection_name}")

        # enable_dynamic_field 允许动态添加字段，自动id
        schema = milvus_client.create_schema(enable_dynamic_field=True, )
        schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True, description="主键id",
                         auto_id=True, )
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, description="实体名称或商品名称",
                         max_length=256)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, description="标题",
                         max_length=256)
        schema.add_field(field_name="parent_title", datatype=DataType.VARCHAR, max_length=256, description="父标题",
                         nullable=True, default_value="")
        schema.add_field(field_name="part", datatype=DataType.INT64, description="如有切片，切片的块号")
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, description="源文件标题", max_length=512)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, description="切分块的内容", max_length=65535)
        schema.add_field(field_name="dense", datatype=DataType.FLOAT_VECTOR, description="用item_name嵌入来的稠密向量",
                         dim=model_vector_dimension)
        schema.add_field(field_name="sparse", datatype=DataType.SPARSE_FLOAT_VECTOR,
                         description="用item_name嵌入来的稀疏向量")

        index_params = milvus_client.prepare_index_params()

        """
        用分层导航小世界HNSW为稠密CONSINE向量创建索引,他是图的索引，检索快精度高
        M: 图中每个节点的最大连接数(常用16-64)
        efConstruction: 构建索引时的搜索范围(越大建索引越慢，但精度越高，常用100-200)
        不同数据体量的推荐建议万级：
        10000 条数据：M=16, efConstruction=200
        50000 条数据：M=32, efConstruction=300
        100000 条数据：M=64, efConstruction=400
        """
        index_params.add_index(
            field_name="dense",
            index_name="dense_index",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 200}
        )
        # 稀疏向量索引：专用SPARSE_INVERTED_INDEX+IP，关闭量化保证精度

        index_params.add_index(
            field_name="sparse",
            index_name="sparse_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            # DAAT_MAXSCORE：稀疏向量检索时，只计算可能得高分的维度，跳过大量0值，速度更快。
            # quantization="none"：稀疏向量里的权重是小数，不做压缩，保证精度不丢。
            params={"inverted_index_algo": "DAAT_MAXSCORE", "quantization": "none"}
        )

        milvus_client.create_collection(collection_name=collection_name, schema=schema,
                                        index_params=index_params
                                        )
        logger.info(f"创建集合[{collection_name}]成功")
    else:
        logger.info(f"集合[{collection_name}],直接复用")
    return milvus_client


def step3_handle_delete_same_item_name(milvus_client: MilvusClient, collection_name: str,
                                       chunk_json_data: list, limit: int = 5):
    item_names = [chunk_json_data_item["item_name"] for chunk_json_data_item in chunk_json_data if
                  chunk_json_data_item["item_name"]]
    # 去重
    item_names = list(set(item_names))

    for item_name in item_names:
        safe_item_name = escape_milvus_string(item_name)
        results = milvus_client.query(collection_name=collection_name,
                                      filter=f"item_name == '{safe_item_name}'",
                                      limit=limit
                                      )
        if results and len(results) > 0:
            logger.info(f"集合[{collection_name}]中已存在[{safe_item_name}]")
            chunk_ids = [result.get("chunk_id") for result in results]
            milvus_client.delete(collection_name=collection_name,
                                 ids=chunk_ids
                                 )
            logger.info(f"删除集合[{collection_name}]中已存在[{item_name}]")


def step4_handle_insert_data(milvus_client, chunk_json_data, collection_name):
    # logger.info(f"进入函数{chunk_json_data}")
    res = milvus_client.insert(collection_name=collection_name,
                               data=chunk_json_data
                               )

    if not res.get("insert_count", 0) or len(res.get("ids", [])) != len(chunk_json_data):
        raise RuntimeError("milvus插入数据失败")

    ids = res.get("ids", [])
    target_chunk_json_data = [{**chunk_json_data_item, "chunk_id": ids[chunk_ind]} for chunk_ind, chunk_json_data_item
                              in
                              enumerate(chunk_json_data)]

    logger.info(f"新插入集合res{target_chunk_json_data}")
    return target_chunk_json_data


def node_chunk_embeddinged_to_milvus(state: ImportGraphState):
    func_name = sys._getframe().f_code.co_name
    add_running_task(state["task_id"], func_name)
    logger.info(f"进入了函数{func_name}")

    # 1. 提取state中的要用到的参数chunks, 并做校验
    chunk_json_data = step1_validate_params(state)

    # 2. 准备好milvus的连接, 准备好要插入milvus的collection, 没有就创建，然后根据chunk结构添加列, 有primary_key(自生成变chunk_id)

    milvus_client = step2_prepare_milvus_connection(collection_name=milvus_config.chunks_collection,
                                                    )

    # 3.判断collection下有没有同名的item_name，有就删除，保证数据是最新的
    step3_handle_delete_same_item_name(milvus_client=milvus_client, collection_name=milvus_config.chunks_collection,
                                       chunk_json_data=chunk_json_data)

    # 插入milvus 数据
    updated_chunks = step4_handle_insert_data(milvus_client=milvus_client, chunk_json_data=chunk_json_data,
                                              collection_name=milvus_config.chunks_collection)
    state["chunks"] = updated_chunks

    logger.info(f"离开了函数{func_name}")
    return state


if __name__ == '__main__':
    # --- 单元测试 ---
    dim = 1024

    test_state = create_default_state(
        task_id="test_milvus_task",
        chunks=[
            {
                "content": "你好啊",
                "title": "测试标题",
                "item_name": "测试项目_Milvus",  # 必须有 item_name，用于幂等清理
                "parent_title": "",
                "part": 1,
                "file_title": "test.pdf",
                "dense": [0.1] * dim,  # 模拟 Dense Vector
                "sparse": {1: 0.5, 10: 0.8}  # 模拟 Sparse Vector
            },
            {
                "content": "你好2222啊",
                "title": "测试标321321321题",
                "item_name": "方面肯33定是付了款第三方立卡手打",  # 必须有 item_name，用于幂等清理
                "part": 1,
                "file_title": "test.pdf",
                "dense": [0.4] * dim,  # 模拟 Dense Vector
                "sparse": {1: 0.5, 10: 0.8}  # 模拟 Sparse Vector
            }
        ]
    )

    print("正在执行 Milvus 导入节点测试...")
    try:
        # 检查必要的环境变量
        if not os.getenv("MILVUS_URL"):
            print("❌ 未设置 MILVUS_URL，无法连接 Milvus")
        elif not os.getenv("CHUNKS_COLLECTION"):
            print("❌ 未设置 CHUNKS_COLLECTION")
        else:
            # 执行节点函数
            result_state = node_chunk_embeddinged_to_milvus(test_state)

            # 验证结果
            chunks = result_state.get("chunks", [])
            if chunks and chunks[0].get("chunk_id"):
                print(f"✅ Milvus 导入测试通过，生成 ID: {chunks[0]['chunk_id']}")
            else:
                print("❌ 测试失败：未能获取 chunk_id")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
