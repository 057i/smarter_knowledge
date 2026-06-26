import sys

from core.logger import logger

"""
该节点将rrf节点和用mcp搜索的结果进行重排序

"""


def step1_format_chunks():
    pass


def step2_generate_rerank_chunks(merged_standard_chunks):
    pass


def step3_generate_topk_chunks(rerank_chunks):
    pass


def decorator_result_by_llm(state):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    rrf_chunks = state["rrf_chunks"]
    web_search_docs = state["web_search_docs"]

    # 1.合并切片
    merged_standard_chunks = step1_format_chunks()

    # 2.用重排序模型生成重排序切片
    rerank_chunks = step2_generate_rerank_chunks(merged_standard_chunks)

    # 3.动态取topk,防止断崖
    topk_chunks = step3_generate_topk_chunks(rerank_chunks)

    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
    # reranked_docs
