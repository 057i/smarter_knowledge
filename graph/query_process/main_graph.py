from langgraph.graph import StateGraph, END
from core.logger import logger
from graph.query_process.nodes.answer_question import answer_question
from graph.query_process.nodes.query_hyde_result_by_embedding import (
    query_hyde_result_by_embedding,
)

from graph.query_process.nodes.decorator_result_by_llm import decorator_result_by_llm

from graph.query_process.nodes.query_result_by_embedding import (
    query_result_by_embedding,
)
from graph.query_process.nodes.order_embedding_result_by_rrf import (
    order_embedding_result_by_rrf,
)
from graph.query_process.nodes.order_result_by_rerank import order_result_by_rerank
from graph.query_process.nodes.query_result_by_mcp import query_result_by_mcp
from graph.query_process.nodes.confirm_item_name_by_user_query import (
    confirm_item_name_by_user_query,
)
from graph.query_process.state import QueryState

query_graph_builder = StateGraph(state_schema=QueryState)
"""
步骤
1.confirm_item_name_by_user_query    从历史会话中取出10条会话数据，拼接当前用户提问，判断是不是有实体,取代代词他/她/它，有需要则进行问题的重写
2.路径判断走


"""

# 确定问题实体
query_graph_builder.add_node(
    "confirm_item_name_by_user_query", confirm_item_name_by_user_query
)

# 用第三方mcp搜索结果
query_graph_builder.add_node("query_result_by_mcp", query_result_by_mcp)

# 用户问题向量化后进行混合搜索
query_graph_builder.add_node("query_result_by_embedding", query_result_by_embedding)

# 只使用模型生成预设性结果，到milvus中进行混合检索
query_graph_builder.add_node(
    "query_hyde_result_by_embedding", query_hyde_result_by_embedding
)
query_graph_builder.add_node(
    "order_embedding_result_by_rrf", order_embedding_result_by_rrf
)
query_graph_builder.add_node("order_result_by_rerank", order_result_by_rerank)
query_graph_builder.add_node("decorator_result_by_llm", decorator_result_by_llm)
query_graph_builder.add_node("answer_question", answer_question)

query_graph_builder.set_entry_point("confirm_item_name_by_user_query")


def confirm_route(state: QueryState):
    answer = state["answer"]
    if answer:
        """
        answer有值的场景：
        1.如果用户问的太模糊且加上历史上下文查不到结果，answer有值
        2.查询到知识库中无实体或有实体但召回评分过低，answer有值
        """

        return "answer_question"
    # 三路并行
    return (
        "query_result_by_embedding",
        "query_hyde_result_by_embedding",
        "query_result_by_mcp",
    )


query_graph_builder.add_conditional_edges(
    "confirm_item_name_by_user_query",
    confirm_route,
    {
        "answer_question": "answer_question",
        "query_result_by_embedding": "query_result_by_embedding",
        "query_hyde_result_by_embedding": "query_hyde_result_by_embedding",
        "query_result_by_mcp": "query_result_by_mcp",
    },
)

# 三路并行搜索，手动rrf融合算出最终排名，rrf适合做粗排，只看排名
query_graph_builder.add_edge(
    "query_result_by_embedding", "order_embedding_result_by_rrf"
)
query_graph_builder.add_edge(
    "query_hyde_result_by_embedding", "order_embedding_result_by_rrf"
)
query_graph_builder.add_edge("query_result_by_mcp", "order_embedding_result_by_rrf")

# 因为rerank一般很贵，所以rerank放在最后，他适合做精排
query_graph_builder.add_edge("order_embedding_result_by_rrf", "order_result_by_rerank")
query_graph_builder.add_edge("order_result_by_rerank", "decorator_result_by_llm")
query_graph_builder.add_edge("decorator_result_by_llm", "answer_question")
query_graph_builder.add_edge("answer_question", END)

query_graph = query_graph_builder.compile()

logger.info(f"query_graph:{query_graph.get_graph().print_ascii()}")
