import os

from dotenv import load_dotenv, find_dotenv
from modelscope.hub.snapshot_download import snapshot_download

from conf.reranker_config import reranker_config
from core.logger import logger

load_dotenv(find_dotenv())
model_dir = snapshot_download(model_id=reranker_config.bge_reranker_name,
                              cache_dir=reranker_config.bge_reranker_path)

logger.info(f"模型已下载到{model_dir}")
