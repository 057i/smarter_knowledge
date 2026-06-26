import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from utils.path_util import PROJECT_ROOT

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)


@app.get("/query_knowledge")
async def query_knowledge():
    """
    知识库查询接口
    :return:
    """




@app.get("/chat.html", response_class=FileResponse)
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


if __name__ == "__main__":
    uvicorn.run("service:query_process:app", host="0.0.0.0", port=8000, reload=True)
