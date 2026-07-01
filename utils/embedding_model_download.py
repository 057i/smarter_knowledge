from dotenv import load_dotenv, find_dotenv
from modelscope.hub.snapshot_download import snapshot_download

from conf import embedding_config
from core.logger import logger

load_dotenv(find_dotenv())
model_dir = snapshot_download(embedding_config.bge_m3, cache_dir=embedding_config.bge_m3_path)

logger.info(f"模型已下载到{model_dir}")
