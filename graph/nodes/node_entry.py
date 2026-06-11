import sys
from pathlib import Path

from core.logger import logger
from graph.state import ImportGraphState
from utils.task_utils import add_running_task, add_done_task


def node_entry(state: ImportGraphState):
    """
    当前节点做的事
    1.sse添加任务事件发送给前端,在开始和结束时候发
    2.校验文件是否存在，存在的话还需要继续校验是md/pdf还是其他文件
    """

    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了节点{func_name}")
    # 告诉前端开始任务了
    add_running_task(state["task_id"], func_name)

    local_file_path = state["local_file_path"]
    # 校验文件是否存在
    if not local_file_path:
        logger.error("f{func_name}运行错误，文件{local_file_path}不存在")
        return state

    # 带后缀名称
    file_name_with_suffix = local_file_path
    # 不带后缀名称
    file_name_without_suffix = Path(local_file_path).stem

    # 如果文件是md文件
    if file_name_with_suffix.endswith(".md"):
        state["is_md_read_enable"] = True
        state["md_path"] = local_file_path
        state["file_title"] = file_name_without_suffix
    elif file_name_with_suffix.endswith(".pdf"):
        state["is_pdf_read_enable"] = True
        state["pdf_path"] = local_file_path
        state["file_title"] = file_name_without_suffix
    else:
        logger.error(f"节点{func_name}运行错误，{file_name_with_suffix}是不支持的文件类型")
        return state

    add_done_task(state["task_id"], func_name)

    return state
