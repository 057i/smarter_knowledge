import json

import sys

from core.logger import logger
from graph.main_graph import graph
from graph.state import create_default_state

logger.info("===== 开始测试 =====")

initial_state = create_default_state(local_file_path="万用表RS-12的使用.pdf", is_pdf_read_enable=True)
final_state = None

# 只输出更最终的状态值（字典形式），不包含节点名称、执行日志、元数据等额外信息
for event in graph.stream(initial_state):
    for key, value in event.items():
        logger.info(f"节点: {key}")
        final_state = value

# 格式化输出最终状态
logger.info(f"最终状态: {json.dumps(final_state, indent=4, ensure_ascii=False)}")

logger.info("图结构:")
# uv add grandalf
graph.get_graph().print_ascii()

logger.info("===== 测试结束 =====")
