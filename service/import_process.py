import os
import shutil
import uuid
from datetime import datetime
from typing import List, Dict, Any

import uvicorn
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from core.logger import logger
from graph.import_process.main_graph import knowledge_import_graph
from graph.import_process.state import create_default_state
from utils.path_util import PROJECT_ROOT
from utils.task_util import add_running_task, add_done_task, update_task_status, get_task_status, get_done_task_list, \
    get_running_task_list, clear_task

app = FastAPI(title="embedding服务", description="embedding服务")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_knowledge_task(task_id: str, file_path: str, local_dir: str):
    """
        构建运行的知识库任务
    """
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

        update_task_status(task_id, "completed")
        add_done_task(state["task_id"], "__end__")
        logger.info("知识库任务构建完成")
    except Exception as e:
        update_task_status(task_id, "failed")

        logger.error(f"构建任务失败：{e}")


@app.post("/upload_file", summary="批量文件上传")
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

    for file in files:
        # 上传文件
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        add_running_task(task_id, "upload_file")

        file_path = today_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"文件已保存到本地，文件路径：{str(file_path)}")

        add_done_task(task_id, "upload_file")

        # 运行构建langgraph知识库任务
        # 构建任务文件夹
        task_dir = PROJECT_ROOT / "output" / file_path.stem
        task_dir.mkdir(parents=True, exist_ok=True)

        background_tasks.add_task(build_knowledge_task, task_id=task_id, file_path=str(file_path),
                                  local_dir=str(task_dir))
    #
    return JSONResponse(status_code=200,
                        content={"message": "文件上传成功,开始构建知识库任务...", "task_ids": task_ids, })


# 先放这里测试，后面抽离到前端项目中去
@app.get("/import.html", response_class=FileResponse)
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


@app.get("/status/{task_id}", summary="查询图节点任务状态")
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


if __name__ == "__main__":
    uvicorn.run("service.import_process:app", host="0.0.0.0", port=8001, reload=True)
