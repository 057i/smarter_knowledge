import sys

from core.logger import logger
from graph.import_process.state import ImportGraphState, create_default_state
from utils.embedding_util import get_bge_m3_ef, generate_embeddings

"""
该节点用来将切分的文档利用embedding模型，来生成对应的稠密和稀疏向量，因为稀疏向量是用点积做的，
所以对系数向量在进行一次L2归一化，消除权重偏差，步骤分为
1.加载数据并校验 state中的chunks
2.加载embedding模型
3.批量生成双路向量  稠密和稀疏
4.更新state状态  将稠密和稀疏向量存起来给后续节点用
"""


def step1_validate_params(state: ImportGraphState) -> list:
    chunks = state.get("chunks", [])
    if not chunks or len(chunks) == 0:
        logger.error("切块数据为空")
        raise ValueError("切块数据为空")

    logger.info(f"切块数据长度为{len(chunks)}")
    return chunks


def step2_load_embedding_model():
    try:
        embedding_model = get_bge_m3_ef()
        if not embedding_model:
            raise ValueError("加载embedding模型失败")
        logger.info("加载embedding模型成功")
        return embedding_model
    except Exception as e:
        logger.error(f"加载embedding模型失败：{str(e)}")
        raise ValueError(f"加载embedding模型失败：{str(e)}")  # 不吞异常，向上传递让调用方做重试/降级处理


def step3_generate_embeddings(required_chunks: list):
    # 防止性能瓶颈，批量生成embedding
    # 几乎所有的 Embedding 模型（尤其是基于 BERT 架构的），对前 128 个 token 的注意力是最集中的。越往后的词，对最终向量方向的拉扯力越弱。
    # 由于注意力前置，所以这里把要嵌入的文本进行处理，处理成实体名/商品名 + content 格式

    batch_size = 5
    embeddings = {
        "dense": [],  # 稠密
        "sparse": []  # 稀疏
    }

    for i in range(0, len(required_chunks), batch_size):
        batch_chunks = required_chunks[i:i + batch_size]

        batch_texts = [
            f"'商品名/实体名:'+{batch_chunk['item_name'] + '，' if batch_chunk.get('item_name') else ''}{'介绍：' + batch_chunk['content'] if batch_chunk.get('content') else ''}"
            for batch_chunk in batch_chunks]

        batch_texts_embedding = generate_embeddings(texts=batch_texts)

        print(type(batch_texts_embedding))
        if batch_texts_embedding.get("dense"):
            embeddings["dense"].extend(batch_texts_embedding["dense"])

        if batch_texts_embedding.get("sparse"):
            embeddings["sparse"].extend(batch_texts_embedding["sparse"])

    chunks_with_embedding = [{**required_chunk, "dense": embeddings["dense"][required_chunk_ind],
                              "sparse": embeddings["sparse"][required_chunk_ind]} for required_chunk_ind, required_chunk
                             in enumerate(required_chunks)]

    logger.info(f"为实体生成向量完成")
    return chunks_with_embedding


def node_document_chunk_embedding(state: ImportGraphState):
    logger.info(f"进入了函数{sys._getframe().f_code.co_name}")

    # 1.加载需要的数据
    required_chunks = step1_validate_params(state)
    #
    # 2.加载embedding模型
    step2_load_embedding_model()

    # 3.批量生成双路向量  稠密和稀疏
    output_chunks = step3_generate_embeddings(required_chunks)

    # 4.更新state状态  将稠密和稀疏向量存起来给后续节点用
    state["chunks"] = output_chunks
    logger.info(f"离开了函数{sys._getframe().f_code.co_name}，state状态为：{state}")

    return state


if __name__ == '__main__':
    chunks = [  # 模拟带item_name的文本切片（上游商品名称识别节点产出）
        {
            "content": "这是一个测试文档的内容，用于验证向量化是否成功。",
            "title": "测试文档标题",
            "item_name": "测试项目",
            "file_title": "测试文件.pdf"
        },
        {
            "content": "这是第二个测试文档的内容，用于验证批量处理逻辑。",
            "title": "测试文档标题2",
            "item_name": "测试项目",
            "file_title": "测试文件.pdf"
        }
    ]
    state = create_default_state(
        chunks=chunks
    )
    node_document_chunk_embedding(state)
