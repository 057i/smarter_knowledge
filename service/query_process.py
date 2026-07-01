import uvicorn
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

from clients.mongo_client import get_messages_by_session_id, delete_messages_by_session_id, add_message
from core.logger import logger
from graph.query_process.main_graph import query_graph
from graph.query_process.state import create_default_query_state
from utils.path_util import PROJECT_ROOT
from utils.sse_util import create_sse_queue, sse_generator
from utils.task_util import update_task_status, get_task_result, clear_task, get_task_id_by_session_id, \
    get_current_session_running_tasks

# 改用 APIRouter
router = APIRouter(
    tags=["查询服务"]
)


@router.get("/query_knowledge")
async def query_knowledge():
    """
    知识库查询接口
    :return:
    """


@router.get("/chat.html", response_class=FileResponse)
async def chat():
    """
        知识库配套查询html静态页
    :return:
    """
    html_absolute_dir = PROJECT_ROOT / "pages" / "chat.html"
    if not html_absolute_dir.exists():
        raise HTTPException(status_code=404, detail="chat.html page not found")

    return FileResponse(
        path=html_absolute_dir,
        media_type="text/html"
    )


class QueryRequest(BaseModel):
    """
    知识库查询参数
    """
    query: str = Field(..., description="查询内容,必传")
    session_id: str = Field(None, description="会话id,必传")
    is_stream: bool = Field(False, description="是否流式返回结果")


def query_by_graph(_query: str, session_id: str, task_id: str, is_stream: bool):
    """

    :param session_id:
    :param _query:
    :param task_id:
    :param is_stream:
    :return:
    """
    update_task_status(task_id, "processing", is_stream)
    state = create_default_query_state(
        session_id=session_id,
        original_query=_query,
        task_id=task_id,
        is_stream=is_stream
    )

    try:

        query_graph.invoke(state)
        update_task_status(task_id, "completed", is_stream)


    except Exception as e:
        update_task_status(task_id, "failed", is_stream)
        logger.exception(f"查询流程失败：{e}")


@router.post("/query")
async def query(query_request: QueryRequest, background_tasks: BackgroundTasks):
    logger.info(f"query: {query_request}")
    _query = query_request.query or ""
    is_stream = query_request.is_stream or False
    session_id = query_request.session_id
    task_id = get_task_id_by_session_id(session_id)

    if not get_task_id_by_session_id:
        return JSONResponse(status_code=400, content={"message": "当前有任务正在进行，请稍后再试"})

    create_sse_queue(session_id)
    if is_stream:
        "流式处理调用invoke慢慢返回结果"
        background_tasks.add_task(query_by_graph, _query, session_id, task_id,
                                  is_stream)
        return JSONResponse(status_code=200,
                            content={

                                "message": "ok",
                                "code": 0,
                                "data": {
                                    "session_id": session_id,
                                    "task_id": task_id,
                                    "is_stream": is_stream
                                }
                            })
    else:
        query_by_graph(_query, session_id, task_id, is_stream)
        answer = get_task_result(session_id, "answer")
        return JSONResponse(status_code=200,
                            content={
                                "data": {
                                    "answer": answer,
                                    "task_id": task_id,
                                    "code": 0,
                                },
                                "message": "查询结果成功",
                            },
                            )


@router.get("/stream/{session_id}")
def stream(session_id: str, request: Request):
    """
    sse 流式返回结果
    :param request: 请求
    :param session_id:
    :return:
    """
    logger.info(f"session_id: {session_id},建立sse连接完成")

    return StreamingResponse(
        sse_generator(session_id, request),  # 第一个参数要是生成器函数，执行返回yield,不执行直接return
        media_type="text/event-stream",
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 10):
    """
    获取历史记录
    :param limit:
    :param session_id:
    :return:
    """
    history = get_messages_by_session_id(session_id=session_id, limit=limit)
    logger.info(f"history: {history}")
    return JSONResponse(status_code=200, content={
        "data": {
            "history": history,
        },
        "code": 0,
        "message": "ok"})


@router.get("/tasks/{session_id}")
async def get_tasks(session_id: str) -> list:
    """
    获取当前会话的任务
    :param session_id:
    :return:
    """
    tasks = get_current_session_running_tasks(session_id)

    return JSONResponse(status_code=200, content={
        "data": {
            "tasks": tasks,
            "session_id": session_id
        },
        "code": 0,
        "message": "ok"})


@router.delete("/history/{session_id}")
async def delete_history(session_id: str):
    """
        刪除历史记录
    """
    delete_count = delete_messages_by_session_id(session_id=session_id)
    logger.info(f"delete_count: {delete_count}")
    return JSONResponse(status_code=200, content={
        "message": "ok",
        "data": {
            "count": delete_count},
        "code": 0,

    })


#

if __name__ == "__main__":
    uvicorn.run("service.query_process:app", host="0.0.0.0", port=8002, reload=True)
