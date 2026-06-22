import copy
from typing import TypedDict


class ImportGraphState(TypedDict):
    task_id: str  # 任务 id  追踪日志用

    #     流程控制标记判断是什么类型文件 这里只开启md和pdf的  后续加上其他类型文件标识
    is_md_read_enable: bool  # 是否开启md文件读取
    is_pdf_read_enable: bool  # 是否开启pdf文件读取

    #     切块相关
    is_normal_split_enable: bool  # 是否开启普通切块
    is_silicon_flow_api_enabled: bool
    is_advanced_split_enabled: bool
    is_vllm_enabled: bool

    #     路径相关
    local_dir: str  # 原始输入文件夹  项目下的output文件夹
    local_file_path: str  # 原始输入文件路径 和pdf_path或md_path文件路径一致
    file_title: str  # 文件标题
    pdf_path: str  # pdf文件路径
    md_path: str  # md文件路径
    split_path: str  # 分块文件路径
    embedding_path: str  # embedding文件路径

    #     内容数据
    md_content: str  # md文件内容
    chunks: list  # 切块数据,后续做双路embedding的字段，包含metadata
    item_name: str  # 主体名称，用于增强检索

    #     数据库相关
    embedding_content: list  # 向量数据的列表，准备写入milvus


# 默认值
graph_default_state: ImportGraphState = {
    "task_id": "",
    "is_pdf_read_enable": False,
    "is_md_read_enable": False,
    "is_normal_split_enabled": True,
    "is_silicon_flow_api_enabled": True,
    "is_advanced_split_enabled": False,
    "is_vllm_enabled": False,
    "local_dir": "",
    "local_file_path": "",
    "pdf_path": "",
    "md_path": "",
    "file_title": "",
    "split_path": "",
    "embeddings_path": "",
    "md_content": "",
    "chunks": [],
    "item_name": "",
    "embeddings_content": []
}


def create_default_state(**overrides):
    """
    根据传入参数创建新的state默认值
    :param overrides:
    :return:
    """
    state = copy.deepcopy(graph_default_state)
    state.update(**overrides)
    return state


def get_default_state():
    """
    获取state默认值
    :return:
    """
    return graph_default_state
