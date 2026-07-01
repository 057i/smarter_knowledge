import copy
from typing import TypedDict, List


class QueryState(TypedDict):
    session_id: str  # 会话唯一标识
    original_query: str  # 用户原始问题
    task_id: str  # 任务ID

    # 检索过程中的中间数据
    embedding_chunks: list  # 普通向量检索回来的切片
    hyde_embedding_chunks: list  # HyDE 检索回来的切片
    kg_chunks: list  # 图谱检索回来的切片
    web_search_docs: list  # 网络搜索回来的文档

    # 排序过程中的数据
    rrf_chunks: list  # RRF 融合排序后的切片
    reranked_docs: list  # 重排序后的最终 Top-K 文档

    # 生成过程中的数据
    prompt: str  # 组装好的 Prompt
    answer: str  # 最终生成的答案
    is_chit_chat: bool  # 是否为闲聊

    # 辅助信息
    item_names: list[str]  # 提取出的实体名称
    rewritten_query: str  # 改写后的问题
    history: list  # 历史对话记录
    is_stream: bool  # 是否流式输出标记


default_query_state: QueryState = {
    "session_id": "",
    "original_query": "",
    "task_id": "",
    "embedding_chunks": [],
    "hyde_embedding_chunks": [],
    "kg_chunks": [],
    "web_search_docs": [],
    "rrf_chunks": [],
    "reranked_docs": [],
    "prompt": "",
    "answer": "",
    "item_names": [],
    "rewritten_query": "",
    "history": [],
    "is_stream": False,
    "is_chit_chat": False
}


def create_default_query_state(**overrides):
    """
    :param overrides:覆盖更新的默认值参数
    :return:
    """

    state = copy.deepcopy(default_query_state)
    state.update(**overrides)
    return state
