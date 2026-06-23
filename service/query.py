import os

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.logger import logger
from utils.path_util import PROJECT_ROOT

app = FastAPI()

# 跨域中间件配置：解决前端调用后端接口的跨域限制
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有前端域名访问（生产环境建议指定具体域名）
    allow_credentials=True,  # 允许携带Cookie等认证信息
    allow_methods=["*"],  # 允许所有HTTP方法（GET/POST/PUT/DELETE等）
    allow_headers=["*"],  # 允许所有请求头
)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/redirect", summary="重定向")
async def redirect():
    # 重定向
    return RedirectResponse(url='/error')


@app.get("/error", summary="错误")
async def error():
    # 报错
    raise HTTPException(status_code=404, detail="Internal Server Error")


@app.post('/uploadfile')
async def upload(file: UploadFile = File(..., description="单文件上传",
                                         alias="upload_file",  # 别名,默认别名是file,这里把前端的文件名upload_file改为file接收
                                         media_type="application/octet-stream"),
                 remarks: str = ""):
    try:
        # 允许文件类型
        ALLOW_FILE_TYPES = ["image/jpeg", "image/png", "image/gif"]
        if file.content_type not in ALLOW_FILE_TYPES:
            raise HTTPException(status_code=400, detail=f"文件类型不允许,仅支持{','.join(ALLOW_FILE_TYPES)}文件类型")

        upload_file_dir = PROJECT_ROOT / "uploads"
        upload_file_dir.mkdir(exist_ok=True, parents=True)
        upload_file_path = upload_file_dir / file.filename

        CHUNK_SIZE = 1024 * 1024 * 5

        # 流式写入
        with open(upload_file_path, "wb") as buffer:
            while True:
                # 每次读5M,防止大文件阻塞
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                buffer.write(chunk)

        # 返回一个JSON响应
        return JSONResponse(status_code=200, content={"message": "文件上传成功", "code": 0,
                                                      "data": {
                                                          "file_name": file.filename,
                                                          "content-type": file.content_type,
                                                          "size": file.size,
                                                          "save_path": str(upload_file_path),
                                                      }
                                                      })



    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败:{e}")







if __name__ == "__main__":
    import uvicorn

    # app名字是按路径来的，开启热更新
    uvicorn.run("service.query:app", host="0.0.0.0", port=8000, reload=True)
