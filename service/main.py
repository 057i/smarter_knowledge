import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from core.logger import logger

# 创建主应用
app = FastAPI(
    title="Smarter Knowledge API",
    description="知识库导入与查询服务",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

# ==================== 导入子路由 ====================
from service.import_process import router as import_router
from service.query_process import router as query_router
from service.file_manager import router as file_router

# 挂载文件管理路由
app.include_router(file_router)

# 挂载导入服务路由（已经在 router 里设置了 prefix="/import"）
app.include_router(import_router)

# 挂载查询服务路由（根路径，保持前端路径不变）
app.include_router(query_router)


@app.get("/")
async def root():
    """根路径 - API 信息"""
    return {
        "status": "ok",
        "message": "Smarter Knowledge API is running",
        "services": {
            "import": "/import/*",
            "query": "/*"
        },
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return JSONResponse(status_code=200, content={
        "data": {
        },
        "code": 0,
        "message": "ok"})


if __name__ == "__main__":
    logger.info("启动 Smarter Knowledge 主服务")
    uvicorn.run(
        "service.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True
    )
