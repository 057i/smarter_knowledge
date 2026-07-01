import sys

from langchain_community.agent_toolkits.sql import prompt

from clients.milvus_client import create_hybrid_search_requests, hybrid_search, get_milvus_client
from conf.milvus_config import milvus_config
from core.load_prompt import load_prompt
from core.logger import logger
from utils.embedding_util import generate_embeddings
from utils.llm_util import get_llm_client
from utils.task_util import add_running_task, add_done_task

"""
    该节点是只模型生成假设性结果，用假设性结果生成向量，到知识库中查找最相似的几条切片
    步骤
    1.调用模型生成假设性结果
    2.用假设性结果生成向量
    3.到知识库中查找最相似的几条切片
"""


def step1_generate_hyde_result(rewritten_query: str):
    """
    1.调用模型生成假设性结果
    """
    llm = get_llm_client()
    prompt = load_prompt("hyde_prompt", rewritten_query=rewritten_query)
    res = llm.invoke(prompt).content
    return res


def step2_generate_embedding(hyde_doc: str):
    """

    :param hyde_doc:
    :return:
    """
    hyde_doc_chunk = generate_embeddings([hyde_doc])

    dense = hyde_doc_chunk["dense"][0]

    sparse = hyde_doc_chunk["sparse"][0]

    return dense, sparse


def step3_query_similar_chunks(dense: list, sparse: list):
    client = get_milvus_client()

    reqs = create_hybrid_search_requests(
        dense=dense,
        sparse=sparse,
        limit=5
    )

    res = hybrid_search(
        client=client,
        collection_name=milvus_config.chunks_collection,
        reqs=reqs,
        ranker_weights=(0.8, 0.2),
        norm_score=True,
        output_fields=["chunk_id", "content", "item_name"],
        limit=5
    )

    return res[0] if res else []


def query_hyde_result_by_embedding(state):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    add_running_task(state["task_id"], func_name, state["is_stream"])

    rewritten_query = state["rewritten_query"]

    hyde_doc = step1_generate_hyde_result(rewritten_query)
    dense, sparse = step2_generate_embedding(hyde_doc)
    hyde_embedding_chunks = step3_query_similar_chunks(dense, sparse)

    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
    add_done_task(state["task_id"], func_name, state["is_stream"])

    return {
        "hyde_embedding_chunks": hyde_embedding_chunks,
        "hyde_doc": hyde_doc,
    }


if __name__ == "__main__":
    # 模拟测试数据
    test_state = {
        "session_id": "6a3ccf008207c630ca70f890",
        "rewritten_query": "RS PRO RS-12数字万用表的规格什么样",
        "item_names": ["RS PRO RS-12数字万用表"],
        "is_stream": False
    }

    print("\n>>> 开始测试 query_hyde_result_by_embedding 节点...")
    try:
        # 执行节点函数
        result = query_hyde_result_by_embedding(test_state)
        logger.info(f"检索结果汇总：{result}")
        # 验证结果
        chunks = result.get("hyde_embedding_chunks", [])
        print(f"\n>>> 测试完成！检索到 {len(chunks)} 条结果")


    except Exception as e:
        logger.error(f"测试运行失败: {e}", exc_info=True)
