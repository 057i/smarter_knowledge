import json
import sys

from clients.milvus_client import (
    get_milvus_client,
    create_hybrid_search_requests,
    hybrid_search,
)
from clients.mongo_client import get_messages_by_session_id, update_message_item_names_by_id, add_message
from conf.milvus_config import milvus_config
from core.load_prompt import load_prompt
from core.logger import logger
from graph.query_process.state import create_default_query_state, QueryState
from utils.embedding_util import generate_embeddings
from utils.llm_util import get_llm_client
from utils.task_util import add_running_task, add_done_task

"""
该节点是通过获取session_id从mongo中往前拿10条对话当做上下文取代指代词，然后拼接上当前问题，
发给模型，让模型判断实体，能判断出实体=>继续步骤，不能判断出=>润色并结束对话
    
步骤有
1.提取10条历史聊天和问题
2.交给模型识别实体和重写问题
3.有实体=>embedding完通过milvus查知识库
    score>0.85  高可信信 继续步骤
    0.6<score<=0.8  疑似  和上一段生成一起生成待选列表，终端流程和用户交互
    score<0.6  噪音  pass  
  无实体，把answer填充

4.如果有识别实体和重写问题拿到item_names把他向量化去milvus中混合检索一下，取出topk

"""

# 用户最大上下文聊天记录长度
MAX_CONTEXT_LEN = 3000


def step1_get_original_query_and_history(state: QueryState):
    """
    校验，获取origin_query,history元素并返回
    :param state:
    :return:
    """

    try:
        original_query = state["original_query"]
        history = get_messages_by_session_id(session_id=state["session_id"], limit=10)
        if not original_query:
            raise ValueError("original_query错误")

        return original_query, history

    except Exception as e:
        logger.error(f"获取历史记录失败: {e}")
        raise RuntimeError(f"获取历史记录失败{e}")


def step2_is_chit_chat(state: QueryState):
    """
    判断是否是闲聊，要是闲聊不查询库 直接返回
    :param state:
    :return:
    """
    try:
        history = state.get("history", [])
        original_query = state.get("original_query", "")
        prompt = load_prompt("is_chit_chat_message", history=history, query=original_query)
        llm = get_llm_client()
        res = llm.invoke(prompt).content
        res = json.loads(res)
        is_chit_chat = res.get("is_chit_chat", False)
        _answer = res.get("answer", "")
        logger.info(f"判断是否是闲聊结果为：{res},{history},{original_query}")

        if is_chit_chat:
            logger.info("当前为闲聊，不查询库")
            state["is_chit_chat"] = True
            state["answer"] = _answer

        return is_chit_chat

    except Exception as e:
        logger.error(f"判断是否是闲聊失败: {e}")
        raise RuntimeError(f"判断是否是闲聊失败: {e}")


def step3_get_item_names_and_rewritten_query(original_query, history):
    """
    获取实体名称列表和重写后的问题
    :param original_query:
    :param history:
    :return:
    """
    # 截取历史记录
    try:
        global MAX_CONTEXT_LEN
        history_text = "\n".join(map(lambda x: f"[{x["role"]}]:{x["text"]}", history))
        logger.info(f"历史记录为：{history_text}")
        history_text = history_text[:MAX_CONTEXT_LEN]

        prompt = load_prompt(
            "rewritten_query_and_itemnames",
            query=original_query,
            history_text=history_text,
        )
        llm = get_llm_client()
        res = llm.invoke(prompt).content  # 字符串类型返回的，用loads接

        res = json.loads(res)

        logger.info(f"实体名称列表和重写后的问题为：{res}")

        item_names = res.get("item_names", [])
        rewritten_query = res.get("rewritten_query", "")

        return item_names, rewritten_query

    except Exception as e:
        logger.error(f"获取实体名称列表和重写后的问题失败: {e}")
        raise RuntimeError(f"获取实体名称列表和重写后的问题失败: {e}")


def step4_get_embedding_item_names(item_names: list):
    """
    获取实体名称的向量
    :param item_names:
    :return:
    """
    logger.info(f"开始对{','.join(item_names)}进行向量化")
    embedding_item_name = generate_embeddings(item_names)

    return embedding_item_name


def step5_generate_hybird_search(item_names: list, embedding_item_names: list):
    """
    做milvus混合检索
    :param item_names
    :param embedding_item_names:
    :return:
    """
    client = get_milvus_client()
    if not client:
        raise RuntimeError("获取milvus客户端失败")

    collection_name = milvus_config.chunks_collection
    final_matches = []
    for i in range(len(item_names)):
        current_dense = embedding_item_names["dense"][i]
        current_sparse = embedding_item_names["sparse"][i]

        reqs = create_hybrid_search_requests(
            dense=current_dense, sparse=current_sparse
        )
        # reqs = create_hybrid_search_requests()

        res = hybrid_search(
            client,
            collection_name,
            reqs,
            norm_score=True,
            ranker_weights=(1.0, 0),
            limit=5,
            output_fields=["item_name"],
            search_params={'ef': 10}
        )
        matches = []
        # 结果是一个列表包列表
        if res and res[0]:
            for hit in res[0]:
                matches.append({
                    "item_name": hit.get("entity", {}).get("item_name", ""),
                    "score": hit.get("distance", 0.0)
                })

        final_matches.append({
            "extracted_name": item_names[i],
            "matches": matches

        })
    logger.info(f"混合检索结果为：{final_matches}")

    return final_matches


def step6_ensure_itemname_valid(result: list) -> dict:
    """
    对齐实体名且筛除重复和无用项
    :param result:
    :return:
        score>=0.85  确信 继续步骤  只取1条
        0.6<score<0.85  疑似  和上一段生成一起生成待选列表，终端流程和用户交互 可多条
        score<0.6  噪音  pass
    """
    # 确定的实体名字
    confirm_item_names: list[str] = []
    # 待选的实体选项
    options = []

    for item in result:
        item_name = item.get("extracted_name", "").strip()
        # 降序排列分值且筛掉噪音
        matches = item.get("matches", [])
        matches = list(filter(lambda x: x.get("score", 0.0) > 0.6, matches))
        matches = sorted(matches, key=lambda x: x.get("score", 0.0), reverse=True)
        if not item_name or not matches:
            continue
        # 高可信度
        high_match = list(filter(lambda x: x.get("score", 0.0) >= 0.85, matches))

        # 中可信度
        middle_match = list(filter(lambda x: 0.6 <= x.get("score", 0.0) < 0.85, matches))

        # 最高可信度 不选了
        if high_match and len(high_match) == 1:
            confirm_item_names.append(item_name)
            continue
        elif high_match and len(high_match) > 1:
            # 待选,找出相同的实体名

            same_item_names = [x.get("item_name", "") for x in high_match if x.get("item_name", "") == item_name]
            # 没有相同的找第0条最高的
            if same_item_names:
                first_high_match = high_match[0]
                confirm_item_names.append(first_high_match.get("item_name", ""))
                continue
        elif len(middle_match) > 0:
            # 最没有了，有几条算几条，默认取5条
            middle_options = middle_match[:5]
            options.extend(middle_options)
    return {
        "confirm_item_names": list(set(confirm_item_names)),
        "options": options
    }


def step7_check_confirm_information(state: QueryState, session_id: str, valid_result: dict, history: list,
                                    rewritten_query: str):
    """
    检查需要确认的信息，如果有高可信度且唯一  直接进入下一个节点
    如果没有，那就要和用户交互一下问是需要那个产品/实体
    :param state:
    :param session_id:
    :param valid_result:
    :param history:
    :param rewritten_query:
    :return:
    """
    logger.info(f"{history}")
    confirm_item_names = valid_result.get("confirm_item_names", [])
    options = valid_result.get("options", [])
    # 高可信度实体

    if confirm_item_names:
        ready_to_update_history = filter(lambda x: x.get("item_name", "") == "", history)

        # 找到待更新的历史(没有绑定item_name的记录),更新mongo中的item_name，并且更新state中的历史记录
        if ready_to_update_history:
            ids = [ready_to_update_history_item.get("id", "")
                   for ready_to_update_history_item in ready_to_update_history]

            update_message_item_names_by_id(ids=ids, item_names=confirm_item_names)
            history = get_messages_by_session_id(session_id=session_id, limit=10)
            state["history"] = history

        state["item_names"] = confirm_item_names
        state["rewritten_query"] = rewritten_query
        # 旧答案
        if state.get("answer", ""):
            del state["answer"]
        return state

    # 待用户交互的待确认实体

    elif options:
        logger.info(f"待用户交互的待确认实体为：{options}")
        option_names = [option.get("item_name", "") for option in options]
        option_names = list(set(option_names))
        # 只有一个实体的话
        answer = ""

        if len(option_names) == 1:
            answer = f"您是想问{option_names[0]}吗"
        elif len(option_names) > 1:
            option_str = "、".join(option_names)
            answer = f"您是想问以下哪个产品：{option_str}？请明确一下型号。"
        state["answer"] = answer
        state["item_names"] = []
        return state


    else:
        answer = "抱歉，未找到相关产品，请提供准确型号以便我为您查询。"
        state["answer"] = answer
        state["item_names"] = []
        return state


def confirm_item_name_by_user_query(state: QueryState):
    """

    :param state:
    :return:
    """

    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    add_running_task(state["task_id"], func_name, state["is_stream"])

    # 存储用户提问到 MongoDB
    add_message(
        session_id=state["session_id"],
        role="user",
        text=state["original_query"],
        task_id=state["task_id"],
    )

    original_query, history = step1_get_original_query_and_history(state)
    is_chit_chat = step2_is_chit_chat(state)
    if is_chit_chat:
        add_done_task(state["task_id"], func_name, state["is_stream"])
        return state

    item_names, rewritten_query = step3_get_item_names_and_rewritten_query(
        original_query=original_query, history=history
    )

    if item_names:
        state["item_names"] = item_names

    state["rewritten_query"] = rewritten_query or original_query

    embedding_item_names = step4_get_embedding_item_names(item_names=item_names)

    # 去milvus中用稀疏和稠密向量做混合检索，milvus内置混合检索，自己配检索器
    hybrid_search_result = step5_generate_hybird_search(
        item_names=item_names, embedding_item_names=embedding_item_names
    )

    # 5.检索对其，并判实体名是否有效
    valid_result = step6_ensure_itemname_valid(hybrid_search_result)

    # 6.判断是更新会话列表还是和用户做确认实体的操作
    step7_check_confirm_information(state, session_id=state["session_id"], valid_result=valid_result, history=history,
                                    rewritten_query=rewritten_query)
    add_done_task(state["task_id"], func_name, state["is_stream"])

    logger.info(f"离开了函数{func_name}，当前状态为：{state}")
    return state


if __name__ == "__main__":
    state = create_default_query_state(
        session_id="6a3ccf008207c630ca70f890", original_query="他是谁"
    )
    print("进入 step4_generate_hybrid_search")
    confirm_item_name_by_user_query(state)
