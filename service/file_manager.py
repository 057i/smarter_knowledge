import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.logger import logger
from utils.path_util import PROJECT_ROOT

router = APIRouter(prefix="/files", tags=["文件管理"])

# 用户文件根目录
USER_FILES_DIR = PROJECT_ROOT / "output"
USER_FILES_DIR.mkdir(parents=True, exist_ok=True)


class FileInfo(BaseModel):
    """文件信息"""
    name: str
    path: str
    size: int
    is_dir: bool
    created_at: str
    modified_at: str


class RenameRequest(BaseModel):
    """重命名请求"""
    old_name: str
    new_name: str


class DeleteRequest(BaseModel):
    """删除请求"""
    path: str


class ParseToKnowledgeRequest(BaseModel):
    """解析为知识库请求"""
    file_name: str


def get_safe_path(relative_path: str) -> Path:
    """
    获取安全路径，防止路径穿越攻击
    :param relative_path: 相对路径
    :return: 绝对路径
    """
    # 移除开头的斜杠
    relative_path = relative_path.lstrip("/\\")

    # 构建完整路径
    full_path = (USER_FILES_DIR / relative_path).resolve()

    # 确保路径在 USER_FILES_DIR 内
    if not str(full_path).startswith(str(USER_FILES_DIR.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问此路径")

    return full_path


def get_file_info(file_path: Path, base_dir: Path) -> FileInfo:
    """
    获取文件信息
    :param file_path: 文件路径
    :param base_dir: 基础目录
    :return: 文件信息
    """
    stat = file_path.stat()
    relative_path = file_path.relative_to(base_dir)

    return FileInfo(
        name=file_path.name,
        path=str(relative_path).replace("\\", "/"),
        size=stat.st_size if file_path.is_file() else 0,
        is_dir=file_path.is_dir(),
        created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
    )


@router.get("/list")
async def list_files(
        path: str = "",
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",  # name, size, created_at, modified_at (默认按创建时间)
        sort_order: str = "desc"  # asc, desc (默认倒序，最新的在前)
):
    """
    列出指定目录下的所有文件和文件夹（支持分页和排序）
    :param path: 相对路径，默认根目录
    :param page: 页码，从 1 开始
    :param page_size: 每页数量，默认 20
    :param sort_by: 排序字段（name, size, created_at, modified_at），默认按创建时间
    :param sort_order: 排序方向（asc, desc），默认倒序（最新的在前）
    :return: 文件列表
    """
    try:
        target_dir = get_safe_path(path)

        if not target_dir.exists():
            raise HTTPException(status_code=404, detail="目录不存在")

        if not target_dir.is_dir():
            raise HTTPException(status_code=400, detail="路径不是目录")

        # 参数校验
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20
        if page_size > 100:
            page_size = 100

        # 收集所有文件信息
        files = []
        for item in target_dir.iterdir():
            try:
                files.append(get_file_info(item, USER_FILES_DIR))
            except Exception as e:
                logger.warning(f"读取文件信息失败: {item}, 错误: {e}")
                continue

        # 排序
        reverse = (sort_order.lower() == "desc")

        if sort_by == "name":
            # 文件夹在前，文件在后，同类按名称排序
            files.sort(key=lambda x: (not x.is_dir, x.name.lower()), reverse=reverse)
        elif sort_by == "size":
            files.sort(key=lambda x: (not x.is_dir, x.size), reverse=reverse)
        elif sort_by == "created_at":
            files.sort(key=lambda x: (not x.is_dir, x.created_at), reverse=reverse)
        elif sort_by == "modified_at":
            files.sort(key=lambda x: (not x.is_dir, x.modified_at), reverse=reverse)
        else:
            # 默认按名称排序
            files.sort(key=lambda x: (not x.is_dir, x.name.lower()), reverse=reverse)

        # 计算分页
        total = len(files)
        total_pages = (total + page_size - 1) // page_size  # 向上取整

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated_files = files[start_idx:end_idx]

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "ok",
            "data": {
                "current_path": path,
                "files": [f.dict() for f in paginated_files],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_prev": page > 1,
                    "has_next": page < total_pages
                }
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"列出文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出文件失败: {str(e)}")


@router.post("/upload")
async def upload_file(
        file: UploadFile = File(...),
        path: str = ""
):
    """
    上传文件到指定目录
    :param file: 上传的文件
    :param path: 目标目录相对路径
    :return: 上传结果
    """
    try:
        target_dir = get_safe_path(path)
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / file.filename

        # 检查文件是否已存在
        if file_path.exists():
            raise HTTPException(status_code=400, detail=f"文件已存在: {file.filename}")

        # 保存文件
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(f"文件上传成功: {file_path}")

        file_info = get_file_info(file_path, USER_FILES_DIR)

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "上传成功",
            "data": file_info.dict()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/download")
async def download_file(path: str):
    """
    下载文件
    :param path: 文件相对路径
    :return: 文件内容
    """
    try:
        file_path = get_safe_path(path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="路径不是文件")

        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件下载失败: {e}")
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.post("/rename")
async def rename_file(request: RenameRequest):
    """
    重命名文件或文件夹
    :param request: 重命名请求
    :return: 重命名结果
    """
    try:
        old_path = get_safe_path(request.old_name)

        if not old_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        # 构建新路径（同目录下）
        new_path = old_path.parent / request.new_name

        # 检查新路径是否在安全范围内
        get_safe_path(str(new_path.relative_to(USER_FILES_DIR)))

        if new_path.exists():
            raise HTTPException(status_code=400, detail=f"目标名称已存在: {request.new_name}")

        old_path.rename(new_path)

        logger.info(f"重命名成功: {old_path} -> {new_path}")

        file_info = get_file_info(new_path, USER_FILES_DIR)

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "重命名成功",
            "data": file_info.dict()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重命名失败: {e}")
        raise HTTPException(status_code=500, detail=f"重命名失败: {str(e)}")


@router.delete("/delete")
async def delete_file(path: str):
    """
    删除文件或文件夹
    :param path: 文件/文件夹相对路径
    :return: 删除结果
    """
    try:
        target_path = get_safe_path(path)

        if not target_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        # 不允许删除根目录
        if target_path == USER_FILES_DIR:
            raise HTTPException(status_code=403, detail="禁止删除根目录")

        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()

        logger.info(f"删除成功: {target_path}")

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "删除成功",
            "data": {
                "deleted_path": path
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.post("/mkdir")
async def create_directory(path: str, name: str):
    """
    创建新文件夹
    :param path: 父目录相对路径
    :param name: 新文件夹名称
    :return: 创建结果
    """
    try:
        parent_dir = get_safe_path(path)
        parent_dir.mkdir(parents=True, exist_ok=True)

        new_dir = parent_dir / name

        if new_dir.exists():
            raise HTTPException(status_code=400, detail=f"文件夹已存在: {name}")

        new_dir.mkdir()

        logger.info(f"创建文件夹成功: {new_dir}")

        file_info = get_file_info(new_dir, USER_FILES_DIR)

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "创建成功",
            "data": file_info.dict()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建文件夹失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/info")
async def get_file_detail(path: str):
    """
    获取文件详细信息
    :param path: 文件相对路径
    :return: 文件信息
    """
    try:
        file_path = get_safe_path(path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        file_info = get_file_info(file_path, USER_FILES_DIR)

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "ok",
            "data": file_info.dict()
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文件信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.post("/parse_to_knowledge")
async def parse_to_knowledge(request: ParseToKnowledgeRequest, background_tasks: BackgroundTasks):
    """
    将 output 文件夹中的文件解析为知识库
    :param request: 包含 file_name 的请求
    :param background_tasks: 后台任务管理器
    :return: 任务 ID
    """
    try:
        file_name = request.file_name

        # 获取文件完整路径
        file_path = get_safe_path(file_name)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_name}")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail=f"路径不是文件: {file_name}")

        # 检查同名文件夹是否已存在
        task_dir = file_path.parent / file_path.stem
        if task_dir.exists():
            return JSONResponse(status_code=200, content={
                "code": 0,
                "message": f"文件已存在解析记录，请先删除解析同名文件夹: {file_path.stem}",
                "data": {
                    "file_name": file_name,
                }
            })
            raise HTTPException(status_code=409, detail=f"文件已存在解析记录，请先删除同名文件夹: {file_path.stem}")

        # 生成任务 ID
        task_id = str(uuid.uuid4())
        start_time = datetime.now()

        # 为文件创建专属目录（和 import_process 保持一致）
        task_dir.mkdir(parents=True, exist_ok=True)

        # 导入 build_knowledge_task（延迟导入避免循环依赖）
        from service.import_process import build_knowledge_task

        # 添加到后台任务，直接调用已有的 build_knowledge_task
        background_tasks.add_task(
            build_knowledge_task,
            task_id=task_id,
            file_path=str(file_path),
            local_dir=str(task_dir),  # 传递专属文件夹，不是 output 根目录
            file_name=file_name,
            start_time=start_time
        )

        logger.info(f"知识库解析任务已创建: {file_name}, task_id: {task_id}")

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "知识库解析任务已启动",
            "data": {
                "task_id": task_id,
                "file_name": file_name,
                "file_path": str(file_path.relative_to(USER_FILES_DIR)),
                "status": "processing",
                "start_time": start_time.isoformat(),
                "end_time": None
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建知识库解析任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@router.get("/parse_tasks")
async def get_parse_tasks(
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
):
    """
    获取解析任务历史列表（支持分页）
    :param status: 过滤状态（processing/completed/failed），不传则返回全部
    :param page: 页码，从 1 开始
    :param page_size: 每页数量，默认 20
    :return: 任务列表
    """
    try:
        # 参数校验
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20
        if page_size > 100:
            page_size = 100

        # 导入 task_util 方法
        from utils.task_util import _task_list

        # 获取所有任务
        tasks = []
        for task_id, task_info in _task_list.items():
            original_status = task_info.get("status", "")

            # 只要不是 completed，都显示为 processing
            display_status = "completed" if original_status == "completed" else "processing"

            task_data = {
                "task_id": task_id,
                "status": display_status,
                "running_list": task_info.get("running_list", []),
                "done_list": task_info.get("done_list", []),
                "result": task_info.get("result", {})
            }
            tasks.append(task_data)

        # 按状态过滤
        if status:
            tasks = [t for t in tasks if t.get("status") == status]

        # 按任务创建时间排序（task_id 包含时间信息，或者用其他字段）
        # 这里简单按 task_id 倒序
        tasks.sort(key=lambda x: x.get("task_id", ""), reverse=True)

        # 计算分页
        total = len(tasks)
        total_pages = (total + page_size - 1) // page_size  # 向上取整

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated_tasks = tasks[start_idx:end_idx]

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "ok",
            "data": {
                "tasks": paginated_tasks,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_prev": page > 1,
                    "has_next": page < total_pages
                }
            }
        })

    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.get("/parse_task/{task_id}")
async def get_parse_task(task_id: str):
    """
    获取单个解析任务的详细信息
    :param task_id: 任务ID
    :return: 任务详情
    """
    try:
        from utils.task_util import get_task_status, get_done_task_list, get_running_task_list

        original_status = get_task_status(task_id)

        if not original_status:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        # 只要不是 completed，都显示为 processing
        display_status = "completed" if original_status == "completed" else "processing"

        done_list = get_done_task_list(task_id)
        running_list = get_running_task_list(task_id)

        # 获取当前进度步骤
        current_step = None
        if running_list and len(running_list) > 0:
            current_step = running_list[-1]  # 最后一个正在运行的任务
        elif done_list and len(done_list) > 0:
            current_step = done_list[-1]  # 最后一个完成的任务

        task_data = {
            "task_id": task_id,
            "status": display_status,
            "current_step": current_step,
            "running_list": running_list,
            "done_list": done_list,
            "result": {}
        }

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "ok",
            "data": task_data
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务详情失败: {str(e)}")


@router.get("/parse_progress/{task_id}")
async def get_parse_progress(task_id: str):
    """
    获取文件解析的当前进度（简化版，只返回当前步骤）
    :param task_id: 任务ID
    :return: 当前进度
    """
    try:
        from utils.task_util import get_task_status, get_done_task_list, get_running_task_list, _NODE_NAME_TO_CN

        original_status = get_task_status(task_id)

        if not original_status:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

        done_list = get_done_task_list(task_id)
        running_list = get_running_task_list(task_id)

        # 获取当前进度步骤
        current_step = None
        current_step_cn = None

        if running_list and len(running_list) > 0:
            current_step = running_list[-1]  # 最后一个正在运行的任务
            current_step_cn = _NODE_NAME_TO_CN.get(current_step, current_step)
        elif done_list and len(done_list) > 0:
            if original_status == "completed":
                current_step = "__end__"
                current_step_cn = "解析完成"
            else:
                current_step = done_list[-1]  # 最后一个完成的任务
                current_step_cn = _NODE_NAME_TO_CN.get(current_step, current_step)

        # 计算进度百分比（粗略估算）
        total_steps = 7  # 总共大约 7 个主要步骤
        completed_steps = len(done_list)
        progress_percent = min(int((completed_steps / total_steps) * 100), 100)

        return JSONResponse(status_code=200, content={
            "code": 0,
            "message": "ok",
            "data": {
                "task_id": task_id,
                "status": "completed" if original_status == "completed" else "processing",
                "current_step": current_step,
                "current_step_cn": current_step_cn,
                "progress_percent": progress_percent,
                "completed_steps": completed_steps,
                "total_steps": total_steps
            }
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务进度失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取任务进度失败: {str(e)}")
