import sys

from clients.milvus_client import create_hybrid_search_requests, get_milvus_client, hybrid_search
from conf.milvus_config import milvus_config
from core.logger import logger
from utils.embedding_util import generate_embeddings
from utils.task_util import add_running_task, add_done_task

"""
    该节点用来将重写的用户问题向量化后，用混合搜索找到结果放到embedding_chunks
    因为是三路并行节点，所以不能返回state，仅返回要修改的
    步骤
    1.提取重写用户问题
    2.用户问题向量化
    3.混合搜索前5条结果
    4.存入
"""


def get_hybird_result(chunks: dict) -> list:
    current_dense = chunks["dense"][0]
    current_sparse = chunks["sparse"][0]
    logger.info(f"开始做混合搜索，当前用户问题稀疏向量化结果为：{current_sparse}")
    reqs = create_hybrid_search_requests(
        dense=current_dense, sparse=current_sparse
    )
    client = get_milvus_client()

    res = hybrid_search(
        client=client,
        collection_name=milvus_config.chunks_collection,
        reqs=reqs,
        ranker_weights=(0.8, 0.2),
        norm_score=True,
        limit=5,
        output_fields=["chunk_id", "content", "item_name"]
    )
    return res[0] if res else []


def query_result_by_embedding(state):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    add_running_task(state["task_id"], func_name, state["is_stream"])

    rewritten_query = state["rewritten_query"]
    rewritten_query_chunk_list = generate_embeddings([rewritten_query])
    if not rewritten_query_chunk_list:
        raise RuntimeError("用户问题向量化失败")
    embedding_chunks = get_hybird_result(rewritten_query_chunk_list)
    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
    add_done_task(state["task_id"], func_name, state["is_stream"])

    return {"embedding_chunks": embedding_chunks}


if __name__ == "__main__":
    # 模拟测试数据
    test_state = {
        "session_id": "6a3ccf008207c630ca70f890",
        "rewritten_query": "RS PRO RS-12数字万用表的规格什么样",
        "item_names": ["RS PRO RS-12数字万用表"],
        "is_stream": False
    }

    print("\n>>> 开始测试 query_result_by_embedding 节点...")
    try:
        # 执行节点函数
        result = query_result_by_embedding(test_state)
        logger.info(f"检索结果汇总：{result}")
        # 验证结果
        chunks = result.get("embedding_chunks", [])
        print(f"\n>>> 测试完成！检索到 {len(chunks)} 条结果")


    except Exception as e:
        logger.error(f"测试运行失败: {e}", exc_info=True)
