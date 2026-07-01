import uuid
from typing import Dict, List

from FlagEmbedding.finetune.embedder.encoder_only.base import __main__

from core.logger import logger
from utils.sse_util import push_to_session, remove_sse_queue

# ---------------------------
# 内存态任务追踪（单进程）
# ---------------------------

# 从session_id获取对应的的task_id
_session_id_to_task_id: Dict[str, list] = {}
_task_list: Dict[str, Dict] = {}
"""
{
        task_id:{
            running_list:[],正在执行的列表
            done_list:[],完成的列表
            status:''状态
            result:''结果
        }
    }

"""

# key: task_id
# value: 节点名列表（原始英文/节点ID）
_tasks_running_list: Dict[str, List[str]] = {}
_tasks_done_list: Dict[str, List[str]] = {}

# key: task_id
# value: status 字符串（如 pending/processing/completed/failed）
_tasks_status: Dict[str, str] = {}

# key: task_id
# value: 任务结果（例如 query 的 answer）
_tasks_result: Dict[str, Dict[str, str]] = {}

TASK_STATUS_PENDING = "pending"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"

# 节点名 -> 中文名映射（用于前端展示）
# 这里的 key 应与 LangGraph 的 add_node("xxx", ...) 中的节点名一致。
_NODE_NAME_TO_CN: Dict[str, str] = {
    # 构建知识库节点
    "upload_file": "开始上传文件",
    "node_entry": "检查文件",
    "node_pdf_to_md": "识别到当前文件为PDF，开始转换为Markdown文件",
    "node_analysis_md_img": "Markdown图片处理",
    "node_item_name_recognition": "实体名称识别",
    "node_split_document": "文档切片",
    "node_document_chunk_embedding": "生成切片向量",
    "node_chunk_embeddinged_to_milvus": "导入向量库",
    "__end__": "构建知识库",
    "END": "构建知识库",
    # --- Query 流程节点（kb/query_process/main_graph.py）---
    "confirm_item_name_by_user_query": "确认问题产品",
    "order_result_by_rerank": "重排序",
    "order_embedding_result_by_rrf": "倒排融合",
    "query_result_by_mcp": "网络搜索",
    "query_result_by_embedding": "切片搜索",
    "query_hyde_result_by_embedding": "切片搜索(假设性文档)",
    "node_multi_search": "多路搜索",
    "node_query_kg": "查询知识图谱",
    "node_join": "多路搜索合并",
    "answer_question": "生成答案",
}


def _ensure_task(task_id: str) -> None:
    """确保 task_id 对应的数据结构已初始化。"""
    if not _task_list.get(task_id, {}):
        _task_list[task_id] = {
            "running_list": [],
            "done_list": [],
            "status": "",
            "result": {},
        }

        # if task_id not in _tasks_running_list:
        #     _tasks_running_list[task_id] = []
        # if task_id not in _tasks_done_list:
        #     _tasks_done_list[task_id] = []
        # if task_id not in _tasks_result:
        #     _tasks_result[task_id] = {}


def _to_cn(node_name: str) -> str:
    """将节点名转换为中文展示名；若无映射则返回原名。"""
    return _NODE_NAME_TO_CN.get(node_name, node_name)


def add_running_task(task_id: str, node_name: str, is_stream: bool = False) -> None:
    """
    添加“正在运行”的节点任务。

    参数：
    - task_id: 任务ID
    - node_name: 节点名称(节点ID)
    """
    _ensure_task(task_id)
    running = _task_list[task_id].get("running_list", [])
    # 避免重复追加
    if node_name not in running:
        running.append(node_name)

    if is_stream:
        task_push_queue(task_id)


def add_done_task(task_id: str, node_name: str, is_stream: bool = False) -> None:
    """
    添加“已完成”的节点任务，即添加完成状态

    注意：添加已完成任务时，会把同名的“正在运行”任务删除。

    参数：
    - task_id: 任务ID
    - node_name: 节点名称(节点ID)
    """
    _ensure_task(task_id)

    # 1) 从 running 中移除同名节点（可能出现重复，移除所有）
    logger.info(
        f"[task_util]完成前 add_done_task: task_id={task_id}, node_name={node_name}，{_task_list}, {_task_list[task_id]}")

    # 移除
    _task_list[task_id]["running_list"] = list(filter(lambda x: x != node_name, _task_list[task_id]["running_list"]))

    # 2) 追加到 done（保持完成顺序），避免重复（保序去重，不能用 set，否则顺序错乱）

    _task_list[task_id]["done_list"].append(node_name)
    _task_list[task_id]["done_list"] = list(dict.fromkeys(_task_list[task_id]["done_list"]))
    logger.info(
        f"[task_util]完成后 add_done_task: task_id={task_id}, node_name={node_name}，{_task_list}, {_task_list[task_id]}")

    if is_stream:
        task_push_queue(task_id)


def set_task_result(task_id: str, key: str, value: str) -> None:
    """
    存储任务结果字段（如 answer / error）。
    """
    _ensure_task(task_id)
    # _tasks_result[task_id][key] = value
    _task_list[task_id]["result"][key] = value


def get_task_result(task_id: str, key: str, default: str = "") -> str:
    """
    获取任务结果字段（如 answer / error）。
    """
    _ensure_task(task_id)
    return _task_list[task_id].get("result", {}).get(key, default)


def get_task_status(task_id: str) -> str:
    """
    获取当前任务状态。

    参数：
    - task_id: 任务ID

    返回：
    - str: 状态名称；如果未设置过则返回空字符串
    """
    # return _tasks_status.get(task_id, "")
    return _task_list[task_id].get("status", "")


def get_done_task_list(task_id: str) -> List[str]:
    """
    获取已完成节点列表（中文展示）。


    """

    _ensure_task(task_id)
    done = _task_list[task_id].get("done_list", [])
    return [_to_cn(n) for n in done]


def get_running_task_list(task_id: str) -> List[str]:
    """
    获取正在运行节点列表（中文展示）。

    """

    _ensure_task(task_id)

    running = _task_list[task_id].get("running_list", [])
    return [_to_cn(n) for n in running]


def update_task_status(task_id: str, status_name: str, is_stream: bool = False) -> None:
    """
    更新任务状态。

    参数：
    - task_id: 任务ID
    - status_name: 状态名称（字符串）
    - is_stream :是否流式输出
    """
    # _tasks_status[task_id] = status_name

    _ensure_task(task_id)
    _task_list[task_id]["status"] = status_name

    if is_stream:
        task_push_queue(task_id)


def task_push_queue(task_id: str):
    """
    通过队列给前端发消息
    :param task_id:
    :return:
    """
    session_id = get_session_id_by_task_id(task_id)
    push_to_session(session_id, "progress", {
        task_id: {
            "status": _task_list[task_id].get("status", ""),
            "result": _task_list[task_id].get("result", {}),
            "done_list": get_done_task_list(task_id),       # 中文映射
            "running_list": get_running_task_list(task_id)  # 中文映射
        }
    })


#
def clear_task(session_id: str, task_id: str, status: str, answer: str):
    running_list = get_running_task_list(task_id)
    done_list = get_done_task_list(task_id)
    if running_list:
        done_list.extend(running_list)
        running_list = []
        _task_list[task_id] = {
            "running_list": running_list,
            "done_list": done_list,
            "status": status,
            "result": {
                **_task_list[task_id]["result"],
                "answer": answer
            }
        }

    # _tasks_running_list.pop(task_id, None)
    # _tasks_done_list.pop(task_id, None)
    # _tasks_status.pop(task_id, None)
    # _tasks_result.pop(task_id, None)
    remove_sse_queue(session_id)


def get_session_id_by_task_id(task_id: str) -> str:
    """
    通过 task_id 获取 session_id。
    """

    _session_id = ""
    for session_id, session_task_ids in _session_id_to_task_id.items():
        if task_id in session_task_ids:
            _session_id = session_id

    return session_id


def get_current_session_running_tasks(session_id: str) -> list:
    """
    获取当前会话正在运行的任务
    :param session_id:
    :return:
    """
    session_task_ids = _session_id_to_task_id.get(session_id, [])
    current_session_tasks = []
    for task_id, task_info in _task_list.items():
        if task_id in session_task_ids:
            current_session_tasks.append({
                "task_id": task_id,
                "task_info": {
                    "status": task_info.get("status", ""),
                    "result": task_info.get("result", {}),
                    "done_list": get_done_task_list(task_id),       # 中文映射
                    "running_list": get_running_task_list(task_id)  # 中文映射
                }
            })
    return current_session_tasks


def get_task_id_by_session_id(session_id: str):
    """
    # 如果有正在运行的就不生成新的task_id
    :param session_id:
    :return:
    """
    session_task_ids = _session_id_to_task_id.get(session_id, [])
    current_task_id = str(uuid.uuid4())

    # 当前会话一个运行过的任务都没有
    if not session_task_ids:
        _session_id_to_task_id[session_id] = [current_task_id]
    else:
        # 运行过了
        current_session_tasks_status = [task_info["status"] == "progress" for task_id, task_info in _task_list.items()
                                        if
                                        task_id in session_task_ids]

        if any(current_session_tasks_status):
            # 有正在运行
            return ""
        else:
            _session_id_to_task_id[session_id].append(current_task_id)
            _ensure_task(current_task_id)

    return current_task_id
