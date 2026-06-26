import os

from dotenv import load_dotenv, find_dotenv
from modelscope.hub.snapshot_download import snapshot_download

from core.logger import logger

load_dotenv(find_dotenv())
model_dir = snapshot_download(os.getenv("BGE_RERANKER_LARGE_NAME"))
cache_dir = os.getenv("BGE_RERANKER_LARGE_PATH")

logger.info(f"模型已下载到{model_dir}")
