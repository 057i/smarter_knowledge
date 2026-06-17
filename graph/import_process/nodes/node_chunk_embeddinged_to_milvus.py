import sys

from core.logger import logger
from graph.import_process.state import ImportGraphState


def node_chunk_embeddinged_to_milvus(state: ImportGraphState):
    logger.info(f"进入了函数{sys._getframe().f_code.co_name}")

    logger.info(f"离开了函数{sys._getframe().f_code.co_name}")
