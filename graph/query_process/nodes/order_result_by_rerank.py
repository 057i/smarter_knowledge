import sys

from core.logger import logger
from graph.query_process.state import QueryState
from utils.rerank_model_util import get_reranker_model
from utils.task_util import add_running_task, add_done_task

"""
当前节点的任务是收集rrf排序的结果，并上利用mcp搜索的结果，做rrf排序，步骤如下
1.合并rrf与mcp搜索的结果，统一格式
2.利用rerank模型做精排
3.取topk，并且防止断崖



"""
RERANK_MIN_TOP_K = 3  # 最小取topk
RERANK_MAX_TOP_K = 10  # 最大取topk
RERANK_GAP_ABS = 0.5  # 断崖绝对差
RERANK_GAP_RATIO = 0.25  # 断崖相对差


def step1_merge_chunks(state: QueryState) -> list:
    """
        统一chunk格式
    :param state:
    :return:
    """
    web_search_docs = state["web_search_docs"]
    rrf_chunks = state["rrf_chunks"]
    merged_chunks = []

    # 网络搜索字段
    for doc in web_search_docs:
        merged_chunks.append({
            "text": doc.get("snippet", ""),
            "chunk_id": None,  # 兼容旧逻辑保留字段
            "title": doc.get("title", ""),
            "url": doc.get("url", ""),
            "source": "web_search",
        })
    for doc in rrf_chunks:
        entity = doc.get("entity", {})
        merged_chunks.append({
            "text": entity.get("content", ""),
            "chunk_id": entity.get("chunk_id", ""),
            "title": entity.get("title") or entity.get("item_name"),
            "url": "",
            "source": "local",
        })

    return merged_chunks


def step2_rerank_chunks_by_model(rewritten_query: str, merged_chunks: list):
    try:
        rerank_model = get_reranker_model()

        # 转换成二元的，不管是元组还是列表，都行
        ready_computed_setences = [(rewritten_query, chunk["text"]) for chunk in merged_chunks]

        # 直接调用computed_score方法就可以计算，结果是数值越大越好,负无穷到正无穷,返回的是 raw logit
        scores = rerank_model.compute_score(ready_computed_setences)

        # 和分数合并
        merged_chunks_with_score = [{**merged_chunk, "score": scores[chunk_ind]}
                                    for chunk_ind, merged_chunk in enumerate(merged_chunks)]

        merged_chunks_with_score = sorted(merged_chunks_with_score, key=lambda x: x["score"], reverse=True)

        return merged_chunks_with_score

    except Exception as e:
        logger.exception(f"rerank_model.compute_score()发生错误：{str(e)}")
        raise RuntimeError(f"rerank_model.compute_score()发生错误：{e}")


def step3_generate_topk_chunks(reranked_chunks):
    """
    生成topk,并防止断崖，规则有
    1.只有当条数大于最小topk时才防断崖，避免数据过少,出现就截断不取后续的了
    2.绝对差距 后-前 ，相对差距（后-前）/前
    :param reranked_chunks:
    :return:
    """

    min_top_k = RERANK_MIN_TOP_K
    max_top_k = min(RERANK_MAX_TOP_K, len(reranked_chunks))
    gap_abs = RERANK_GAP_ABS
    gap_ratio = RERANK_GAP_RATIO

    top_k = max_top_k
    if max_top_k > min_top_k:

        # 下标0开始
        for i in range(min_top_k - 1, max_top_k - 1):
            current_score = reranked_chunks[i]["score"]
            next_score = reranked_chunks[i + 1]["score"]

            gap = next_score - current_score
            rel = gap / current_score

            if gap >= gap_abs or rel >= gap_ratio:
                # 触发断崖截断
                top_k = i + 1
                break
    target_reranked_chunks = reranked_chunks[:top_k]

    return target_reranked_chunks


def order_result_by_rerank(state: QueryState):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    add_running_task(state["task_id"], func_name, state["is_stream"])

    rewritten_query = state["rewritten_query"]
    # 1.合并rrf与mcp搜索的结果，统一格式
    merged_chunks = step1_merge_chunks(state)

    logger.info(f"合并后的结果为：{merged_chunks}")
    # 2.利用rerank模型做精排
    reranked_chunks = step2_rerank_chunks_by_model(rewritten_query=rewritten_query, merged_chunks=merged_chunks)

    # 3.取topk，并且防止断崖
    topk_chunks = step3_generate_topk_chunks(reranked_chunks=reranked_chunks)

    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
    add_done_task(state["task_id"], func_name, state["is_stream"])

    return {"reranked_docs": topk_chunks}


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(">>> 启动 node_rerank 本地测试")
    print("=" * 50)

    # 1. 模拟数据
    # 1.1 RRF 本地文档数据
    mock_rrf_chunks = [
        {"entity": {"chunk_id": "local_1", "content": "RRF是一种倒数排名融合算法", "title": "算法介绍", "score": 0.9}},
        {"entity": {"chunk_id": "local_2", "content": "BGE是一个强大的重排序模型", "title": "模型介绍", "score": 0.8}},
        {"entity": {"chunk_id": "local_3", "content": "无关的测试文档内容", "title": "测试文档", "score": 0.1}}  # 预期低分
    ]

    # 1.2 MCP 联网搜索数据
    mock_web_docs = [
        {"title": "Rerank技术详解", "url": "http://web.com/1", "snippet": "Rerank即重排序，常用于RAG系统的第二阶段"},
        {"title": "无关网页", "url": "http://web.com/2", "snippet": "今天天气不错，适合出去游玩"}  # 预期低分
    ]

    mock_state = {
        "session_id": "test_rerank_session",
        "rewritten_query": "什么是RRF和Rerank？",  # 查询意图：想了解这两个算法
        "rrf_chunks": mock_rrf_chunks,
        "web_search_docs": mock_web_docs,
        "is_stream": False
    }

    try:
        # 运行节点
        result = order_result_by_rerank(mock_state)

        logger.info(f"测试结果为：{result}")

    except Exception as e:
        logger.exception(f"测试运行期间发生未捕获异常: {e}")
