import os
import shutil
import uuid
from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from core.logger import logger
from graph.import_process.main_graph import knowledge_import_graph
from graph.import_process.state import create_default_state
from utils.path_util import PROJECT_ROOT
from utils.task_util import add_running_task, add_done_task, update_task_status, get_task_status, get_done_task_list, \
    get_running_task_list, clear_task

# 改用 APIRouter 而不是 FastAPI app
router = APIRouter(
    prefix="/import",
    tags=["导入服务"]
)


def build_knowledge_task(task_id: str, file_path: str, local_dir: str, file_name: str = None, start_time: datetime = None):
    """
        构建运行的知识库任务
    """
    if start_time is None:
        start_time = datetime.now()

    if file_name is None:
        from pathlib import Path
        file_name = Path(file_path).name

    update_task_status(task_id, "process")
    state = create_default_state(
        local_file_path=file_path,
        task_id=task_id,
        local_dir=local_dir
    )
    try:
        logger.info("开始构建知识库任务")
        for event in knowledge_import_graph.stream(state):
            for node_name, node_result in event.items():
                logger.info(f"{node_name},{node_result}")
                # add_done_task()
                add_done_task(task_id, node_name)

        end_time = datetime.now()
        update_task_status(task_id, "completed", )
        add_done_task(state["task_id"], "__end__")
        logger.info("知识库任务构建完成")

        # 记录成功日志
        log_success_to_file(task_id, file_path, file_name, start_time, end_time)
    except (TimeoutError, RuntimeError) as e:
        # MinerU 超时或处理失败
        end_time = datetime.now()
        error_msg = f"知识库任务构建失败（MinerU 处理失败）: {e}"
        logger.error(error_msg)
        update_task_status(task_id, "failed")

        # 记录失败日志到文件
        log_failure_to_file(task_id, file_path, file_name, start_time, end_time, error_msg, str(e))
    except Exception as e:
        # 其他未知错误
        end_time = datetime.now()
        error_msg = f"构建任务失败: {e}"
        logger.error(error_msg)
        update_task_status(task_id, "failed")

        # 记录失败日志到文件
        log_failure_to_file(task_id, file_path, file_name, start_time, end_time, error_msg, str(e))


def log_failure_to_file(task_id: str, file_path: str, file_name: str, start_time: datetime, end_time: datetime, error_msg: str, error_detail: str):
    """
    记录失败的任务到 log 目录
    :param task_id: 任务ID
    :param file_path: 文件路径
    :param file_name: 文件名
    :param start_time: 开始时间
    :param end_time: 结束时间
    :param error_msg: 错误消息
    :param error_detail: 错误详情
    """
    try:
        # 创建 log 目录
        log_dir = PROJECT_ROOT / "log"
        log_dir.mkdir(parents=True, exist_ok=True)

        # 生成日志文件名：失败任务_时间戳.txt
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"failed_task_{timestamp}_{task_id[:8]}.txt"

        # 计算耗时
        duration = (end_time - start_time).total_seconds()

        # 写入日志
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"任务失败记录\n")
            f.write(f"=" * 50 + "\n")
            f.write(f"任务ID: {task_id}\n")
            f.write(f"文件名: {file_name}\n")
            f.write(f"文件路径: {file_path}\n")
            f.write(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"耗时: {duration:.2f} 秒\n")
            f.write(f"错误消息: {error_msg}\n")
            f.write(f"错误详情: {error_detail}\n")
            f.write(f"=" * 50 + "\n")

        logger.info(f"失败日志已保存到: {log_file}")
    except Exception as e:
        logger.error(f"保存失败日志时出错: {e}")


def log_success_to_file(task_id: str, file_path: str, file_name: str, start_time: datetime, end_time: datetime):
    """
    记录成功的任务到 log 目录
    :param task_id: 任务ID
    :param file_path: 文件路径
    :param file_name: 文件名
    :param start_time: 开始时间
    :param end_time: 结束时间
    """
    try:
        # 创建 log 目录
        log_dir = PROJECT_ROOT / "log"
        log_dir.mkdir(parents=True, exist_ok=True)

        # 生成日志文件名：成功任务_时间戳.txt
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"success_task_{timestamp}_{task_id[:8]}.txt"

        # 计算耗时
        duration = (end_time - start_time).total_seconds()

        # 写入日志
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"任务成功记录\n")
            f.write(f"=" * 50 + "\n")
            f.write(f"任务ID: {task_id}\n")
            f.write(f"文件名: {file_name}\n")
            f.write(f"文件路径: {file_path}\n")
            f.write(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"耗时: {duration:.2f} 秒\n")
            f.write(f"状态: 成功\n")
            f.write(f"=" * 50 + "\n")

        logger.info(f"成功日志已保存到: {log_file}")
    except Exception as e:
        logger.error(f"保存成功日志时出错: {e}")


@router.post("/upload_file", summary="批量文件上传")
async def upload_file(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """
        文件上传接口
        1.接收前端上传的files,先不传到mino桶里，先暂时存项目下
        2.按日期创建文件夹，上传到指定日期文件夹
        3.为每个文件生成task_id,上传完成后对每个文件启动独立的langgraph知识库构建任务，后台处理任务
        4.实时更新进度，让前端轮巡获取结果

    :param background_tasks:多任务管理器
    :param files: 前端上传文件
    :return:
    """

    today_str = datetime.now().strftime("%Y-%m-%d")
    today_dir = PROJECT_ROOT / "uploads" / "user_uploads" / today_str
    today_dir.mkdir(parents=True, exist_ok=True)

    task_ids = []  # 查询任务的id
    errors = []  # 记录错误

    for file in files:
        # 检查同名文件夹是否已存在
        task_dir = PROJECT_ROOT / "output" / file.filename.rsplit('.', 1)[0]  # 去掉扩展名
        if task_dir.exists():
            errors.append(f"文件 {file.filename} 已存在解析记录，请先删除同名文件夹")
            logger.warning(f"文件上传被拒绝：{file.filename}，原因：同名文件夹已存在")
            continue

        # 上传文件
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        start_time = datetime.now()
        add_running_task(task_id, "upload_file")

        file_path = today_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"文件已保存到本地，文件路径：{str(file_path)}")

        add_done_task(task_id, "upload_file")

        # 运行构建langgraph知识库任务
        # 构建任务文件夹
        task_dir.mkdir(parents=True, exist_ok=True)

        background_tasks.add_task(
            build_knowledge_task,
            task_id=task_id,
            file_path=str(file_path),
            local_dir=str(task_dir),
            file_name=file.filename,
            start_time=start_time
        )

    # 返回结果
    if errors:
        return JSONResponse(status_code=400, content={
            "message": f"部分文件上传失败",
            "task_ids": task_ids,
            "errors": errors
        })

    return JSONResponse(status_code=200, content={
        "message": "文件上传成功,开始构建知识库任务...",
        "task_ids": task_ids,
    })


# 先放这里测试，后面抽离到前端项目中去
@router.get("/import.html", response_class=FileResponse)
async def get_import_page():
    html_abs_path = PROJECT_ROOT / "pages" / "import.html"

    # 校验文件是否存在，不存在则抛出404异常
    if not os.path.exists(html_abs_path):
        logger.error(f"前端页面文件不存在，路径：{html_abs_path}")
        raise HTTPException(status_code=404, detail="import.html page not found")
    # 以FileResponse返回HTML文件，浏览器自动渲染，要是董涛html文档改用HTMLRESPONSE
    return FileResponse(
        path=html_abs_path,
        media_type="text/html"  # 显式指定媒体类型为HTML，确保浏览器正确解析
    )


@router.get("/status/{task_id}", summary="查询图节点任务状态")
async def get_graph_task_process(task_id: str):
    """
    查询任务状态
    :param task_id: 任务id
    :return:
    """
    task_status_info: Dict[str, Any] = {
        "code": 200,
        "task_id": task_id,
        "status": get_task_status(task_id),  # 任务全局状态：pending/processing/completed/failed
        "done_list": get_done_task_list(task_id),  # 已完成的节点/阶段列表
        "running_list": get_running_task_list(task_id)  # 正在运行的节点/阶段列表
    }

    return JSONResponse(status_code=200,
                        content=task_status_info)
