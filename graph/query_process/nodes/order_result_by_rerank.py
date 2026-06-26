import sys

from core.logger import logger


def order_result_by_rerank(state):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")

    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
