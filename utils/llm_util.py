from typing import Optional

from langchain.chat_models import init_chat_model
from langchain_core.exceptions import LangChainException
from sqlalchemy.ext.asyncio import result

from conf.llm_config import llm_config
from core.logger import logger

# 做私有缓存
_llm_client_map = {}


def get_llm_client(model: Optional[str] = None, json_mode: bool = False):
    """
    获取llm客户端
    :param model: 模型名称
    :return:
    """
    target_model = model or llm_config.llm_model or "qwen3-32b"

    # 模型名-json模式 做缓存key值
    key = f"{target_model}-{json_mode}"

    if _llm_client_map.get(key):
        return _llm_client_map[key]

    # extra_body：千问/即梦等国产模型专属私有参数（LangChain透传至API）
    extra_body = {"enable_thinking": False}  # 千问专属：关闭思考链输出，减少冗余内容
    # model_kwargs：OpenAI通用参数，所有兼容API均支持
    model_kwargs = {}

    # 开启JSON标准输出模式，强制模型返回可解析的json_object
    if json_mode:
        model_kwargs["response_format"] = {"type": "json_object"}

    try:
        logger.info(f"开始初始化LLM模型：{llm_config}")
        llm = init_chat_model(model=target_model,
                              api_key=llm_config.api_key,
                              base_url=llm_config.base_url,
                              temperature=llm_config.llm_temperature,
                              extra_body=extra_body,
                              model_kwargs=model_kwargs,
                              model_provider="openai",
                              )
        _llm_client_map[key] = llm
        return llm
    except LangChainException as e:
        logger.error(f"初始化LLM模型失败：{e}")
        raise LangChainException(f"初始化LLM模型失败：{e}")


if __name__ == '__main__':
    """ 
    测试代码
    """
    llm = get_llm_client(model=llm_config.lv_model)
    result = llm.invoke("你是谁")
    print(result.content)
    print(_llm_client_map)
