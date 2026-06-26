import asyncio

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from conf.mcp_config import mcp_config
from core.load_prompt import load_prompt
from core.logger import logger
from utils.llm_util import get_llm_client


async def query_by_mcp_agent(query: str):
    """

    """
    try:
        client = MultiServerMCPClient(
            {
                "bailian_search": {  #
                    "transport": "streamable_http",
                    "url": mcp_config.mcp_base_url,
                    "headers": {"Authorization": mcp_config.api_key},
                    "timeout": 300,
                    "sse_read_timeout": 300,

                }
            }
        )
        tools = await client.get_tools()

        llm = get_llm_client()
        agent = create_agent(model=llm, tools=tools)

        prompt = load_prompt("mcp_prompt", query=query)
        result = await agent.ainvoke({
            "messages": [("user", prompt)]
        })

        logger.info(f"结果：{result["messages"][-1].content}")
        return result["messages"][-1].content
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}", exc_info=True)
        raise RuntimeError(f"获取mcp工具列表失败{e}")


if __name__ == "__main__":
    asyncio.run(query_by_mcp_agent(
        "RS PRO RS-12数字万用表的规格什么样?"))
