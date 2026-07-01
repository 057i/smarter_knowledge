from FlagEmbedding import FlagReranker

from conf.reranker_config import reranker_config
from core.logger import logger

_reranker_model = None


def get_reranker_model():
    global _reranker_model
    logger.info("获取reranker模型")
    if _reranker_model is None:
        # 这个目录要注意，要是下载下面找有config.json那个文件的目录
        _reranker_model = FlagReranker(
            r"D:\ai_models\modelscope_cache\models\rerank\BAAI\bge-reranker-v2-m3\BAAI\bge-reranker-v2-m3",
            device=reranker_config.bge_reranker_device,
            use_fp16=reranker_config.bge_reranker_fp16,
        )
    return _reranker_model
