import json
import sys

from win32com.server import exception

from core.logger import logger
from graph.query_process.nodes.query_hyde_result_by_embedding import query_hyde_result_by_embedding
from graph.query_process.nodes.query_result_by_embedding import query_result_by_embedding

"""
    该节点是对embedding过的节点做rrf重排，取top-k
    
"""


def order_embedding_by_rrf_rank(source_list: list[tuple[list, float]], k: int = 60, limit: int = 10) -> list:
    """
    rrf=weight*(1/(k+rank))
    :param source_list:
    :param k:
    :param limit
    :return:
    """
    try:
        chunk_map = {}
        score_map = {}
        logger.info(f"排序列表：{source_list[0][0]}")
        for chunks, weight in source_list:
            for rank, chunk in enumerate(chunks):

                chunk_json = json.loads(json.dumps(chunk))
                chunk_id = chunk_json.get("id", "")
                chunk_id = str(chunk_id)
                # content = chunk_json.get("entity", {}).get("content", "")
                score = chunk_json.get("distance", 0.0)
                logger.info(f"rrf排序列表：{type(chunk_json)}, {chunk_json}")

                if chunk_id not in score_map:
                    score_map[chunk_id] = 0
                    chunk_map[chunk_id] = chunk_json

                score_map[chunk_id] += weight * (1 / (k + rank))
                logger.info(chunk_id, chunk_json, score)

        chunk_with_score = []
        for chunk_id, score_value in score_map.items():
            chunk_with_score.append(
                (
                    chunk_id, score_value, chunk_map[chunk_id],
                )
            )
        # 降序排列结果
        chunk_with_score = sorted(chunk_with_score, key=lambda x: x[1], reverse=True)

        chunk_with_score = chunk_with_score[:limit]

        return chunk_with_score

    except Exception as e:
        logger.error(f"rrf排序失败: {e}", exc_info=True)
        raise RuntimeError(f"rrf排序失败: {e}")


def order_embedding_result_by_rrf(state):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    embedding_chunks = state["embedding_chunks"]
    hyde_embedding_chunks = state["hyde_embedding_chunks"]
    source_list = [(embedding_chunks, 1.0), (hyde_embedding_chunks, 1.0)]

    order_embedding_by_rrf_result = order_embedding_by_rrf_rank(source_list=source_list, k=60, limit=10)
    rrf_chunks = [result_item[2] for result_item in order_embedding_by_rrf_result]
    logger.info(f"rrf排序结果：{order_embedding_by_rrf_result}")
    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
    return {"rrf_chunks": rrf_chunks}


# ================================
# 本地测试入口
# ================================
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print(">>> 启动 node_rrf 本地测试")
    print("=" * 50)

    mock_state = {
        "session_id": "6a3ccf008207c630ca70f890",
        "is_stream": False,
        "original_query": "RS PRO RS-12数字万用表的规格什么样",
        "rewritten_query": "RS PRO RS-12数字万用表的规格什么样",
        "item_names": ["RS PRO RS-12数字万用表"]
    }

    try:

        emb_res = query_result_by_embedding(mock_state)
        hyde_res = query_hyde_result_by_embedding(mock_state)
        mock_state['embedding_chunks'] = emb_res.get("embedding_chunks") or []
        mock_state['hyde_embedding_chunks'] = hyde_res.get("hyde_embedding_chunks") or []

        result = order_embedding_result_by_rrf(mock_state)
        rrf_chunks = result.get("rrf_chunks", [])

        emb_cnt = len(mock_state.get("embedding_chunks") or [])
        hyde_cnt = len(mock_state.get("hyde_embedding_chunks") or [])

        print("\n" + "=" * 50)
        print(">>> 测试结果摘要:")
        print(f"输入数量: Embedding={emb_cnt}, HyDE={hyde_cnt}")
        print(f"输出数量: {len(rrf_chunks)}")
        print("-" * 30)

        print("最终排名:")
        for i, doc in enumerate(rrf_chunks, start=1):
            print(f"Rank {i}: content={doc}")

        print("=" * 50)

    except Exception as e:
        logger.exception(f"测试运行期间发生未捕获异常: {e}")
