from langgraph.graph import StateGraph, END

from graph.import_process.nodes.node_analysis_md_img import node_analysis_md_img
from graph.import_process.nodes.node_chunk_embeddinged_to_milvus import node_chunk_embeddinged_to_milvus
from graph.import_process.nodes.node_document_chunk_embedding import node_document_chunk_embedding
from graph.import_process.nodes.node_entry import node_entry
from graph.import_process.nodes.node_item_name_recognition import node_item_name_recognition
from graph.import_process.nodes.node_pdf_to_md import node_pdf_to_md
from graph.import_process.nodes.node_split_document import node_split_document

from graph.import_process.state import ImportGraphState

# 配置默认状态
graph_builder = StateGraph(ImportGraphState)

# 配置图节点
graph_builder.add_node("node_entry", node_entry)
graph_builder.add_node("node_pdf_to_md", node_pdf_to_md)
graph_builder.add_node("node_analysis_md_img", node_analysis_md_img)
graph_builder.add_node("node_split_document", node_split_document)
graph_builder.add_node("node_item_name_recognition", node_item_name_recognition)
graph_builder.add_node("node_document_chunk_embedding", node_document_chunk_embedding)
graph_builder.add_node("node_chunk_embeddinged_to_milvus", node_chunk_embeddinged_to_milvus)


def route_after_entry(state: ImportGraphState):
    """
    判断是走哪个条件边
    :param state:
    :return:
    """
    is_md_read_enable = state["is_md_read_enable"]
    is_pdf_read_enable = state["is_pdf_read_enable"]

    if is_md_read_enable:
        return 'node_analysis_md_img'
    elif is_pdf_read_enable:
        return 'node_pdf_to_md'
    else:
        return END


graph_builder.add_conditional_edges("node_entry", route_after_entry, {
    # 名称：节点名称
    "node_analysis_md_img": "node_analysis_md_img",
    "node_pdf_to_md": "node_pdf_to_md",
    END: END
})

graph_builder.set_entry_point("node_entry")
graph_builder.add_edge("node_pdf_to_md", "node_analysis_md_img")
graph_builder.add_edge("node_analysis_md_img", "node_split_document")
graph_builder.add_edge("node_split_document", "node_item_name_recognition")
graph_builder.add_edge("node_item_name_recognition", "node_document_chunk_embedding")
graph_builder.add_edge("node_document_chunk_embedding", "node_chunk_embeddinged_to_milvus")
graph_builder.add_edge("node_chunk_embeddinged_to_milvus", END)

knowledge_import_graph = graph_builder.compile()
