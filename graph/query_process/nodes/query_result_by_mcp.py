import asyncio
import sys

from clients.mcp_client import query_by_mcp_agent
from core.logger import logger
from utils.task_util import add_running_task, add_done_task

"""
该节点的功能是调用mcp搜索，并将搜索内容格式化后存入state,key值是web_search_docs

"""


def query_result_by_mcp(state):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    add_running_task(state["task_id"], func_name, state["is_stream"])

    rewritten_query = state["rewritten_query"]

    _result = asyncio.run(query_by_mcp_agent(query=rewritten_query))

    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
    add_done_task(state["task_id"], func_name, state["is_stream"])

    return {
        "web_search_docs": _result or []
    }


if __name__ == "__main__":
    # 模拟测试数据
    test_state = {
        "session_id": "6a3ccf008207c630ca70f890",
        "rewritten_query": "帮我搜RS PRO RS-12数字万用表参数",
        "item_names": ["RS PRO RS-12数字万用表"],
        "is_stream": False
    }

    print("\n>>> 开始测试 query_hyde_result_by_embedding 节点...")
    try:
        # 执行节点函数
        result = query_result_by_mcp(test_state)
        logger.info(f"检索结果汇总：{result}")
        # 验证结果



    except Exception as e:
        logger.error(f"测试运行失败: {e}", exc_info=True)
