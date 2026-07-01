import queue
import re
import sys

from clients.mongo_client import add_message
from core.load_prompt import load_prompt
from core.logger import logger
from graph.query_process.state import QueryState
from utils.llm_util import get_llm_client
from utils.sse_util import SSEEvent, push_to_session
from utils.task_util import set_task_result, add_running_task, add_done_task, clear_task, get_running_task_list, \
    get_done_task_list

"""
该节点的功能是，检查state，并输出对应回答，遵守以下规则
1.state中的answer如果有答案，说明回答不上来，没提取出对话中的实体，直接返回，如果没答案，继续下面步骤
2.提取state中的变量，生成prompt交给模型生成结果后润色输出（若是输出，要注意是流式还是非流式输出）
3.保存回答到mongodb
4.最后一次输出final_push  触发页面图片渲染的sse
"""


def answer_user(session_id: str, task_id: str, answer: str, is_stream: bool = False, is_no_answer: bool = False):
    """
    返回前端显示最终回答
    :param is_no_answer: 是不是模型没找到答案需要再次交互
    :param task_id:
    :param session_id:
    :param answer:
    :param is_stream:
    :return:
    """
    if is_stream:
        # SSE方式流式输出
        # 仅「没答案/闲聊」场景在这里整段下发；正常答案已经在 step2 逐 token 发过 DELTA，此处不重复
        if is_no_answer:
            # 推 final 前先把当前节点收尾，保证 final 携带的 running_list/done_list 是「已全部完成」状态
            add_done_task(task_id, "answer_question")
            push_to_session(session_id=session_id, event=SSEEvent.FINAL_WITH_NO_ANSWER,
                            data={
                                "task_id": task_id,
                                "answer": answer,
                                "running_list": get_running_task_list(task_id),
                                "done_list": get_done_task_list(task_id),
                            })
    else:
        # 直接返回结果
        set_task_result(task_id, "answer", answer)


def step1_check_answer_exists(state: QueryState):
    """检查是否是从确认不出实体名称跳过来的"""
    _answer = state.get("answer", "")
    if _answer:
        logger.info(f"答案已经存在，直接返回答案：{_answer}")
        answer_user(session_id=state.get("session_id", ""), task_id=state.get("task_id", ""),
                    answer=_answer,
                    is_stream=state.get("is_stream", False),
                    is_no_answer=True)

        return True
    else:

        return False


def step2_generate_prompt_to_llm(state: QueryState):
    _reranked_docs = state.get("reranked_docs", [])
    _item_names = state.get("item_names", [])
    _history = state.get("history", [])
    _rewritten_query = state.get("rewritten_query", "")
    _session_id = state.get("session_id", "")
    _task_id = state.get("task_id", "")
    _is_stream = state.get("is_stream", False)

    docs_str = ""
    image_urls = []
    for ind, _reranked_doc in enumerate(_reranked_docs, start=1):
        # 正则匹配图片，提取图片地址并删除图片标签
        _text = _reranked_doc.get("text", "")
        image_urls.extend(re.findall(r'!\[[^\]]*\]\(([^)]+)\)', _text))
        clean_text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', _text)
        docs_str += f"[{ind}][参考来源:{_reranked_doc.get('source', '')}]\n[内容：{clean_text}][参考评分:{_reranked_doc.get('score', '')}]\n"

    prompt = load_prompt("answer_question", context=docs_str,
                         item_names=_item_names, history=_history,
                         question=_rewritten_query)
    llm = get_llm_client()

    # 非流式：一次性返回
    if not _is_stream:
        res = llm.invoke(prompt).content
        return res, image_urls

    # 流式：逐 token 推送 DELTA，实现前端打字机效果
    res = ""
    for chunk in llm.stream(prompt):
        delta = chunk.content or ""
        if not delta:
            continue
        res += delta
        push_to_session(session_id=_session_id, event=SSEEvent.DELTA, data={
            "task_id": _task_id,
            "delta": delta,
        })

    return res, image_urls


def step3_save_llm_answer_message_to_mongodb(state, image_urls: list = []):
    """
    将查询结果写入数据库
    :param state:
    :param image_urls:
    :return:
    """
    _session_id = state["session_id"]
    _item_names = state.get("item_names", [])
    _answer = state.get("answer", "")
    _rewritten_query = state.get("rewritten_query", "")
    _task_id = state.get("task_id", "")
    try:
        if _answer:
            add_message(
                session_id=_session_id,
                item_names=_item_names,
                rewritten_query=_rewritten_query,
                role="assistant",
                text=_answer,
                message_id="",
                task_id=_task_id,
                image_urls=image_urls
            )
    except Exception as e:
        logger.error(f"保存LLM回答到MongoDB时出错：{e}")


def step4_output_answer(session_id: str = "", answer: str = "", image_urls: list[str] = []):
    # 格式化成文字和图片分开

    image_str = "\n".join([f"<image_url src={image_url}/>" for image_url in image_urls])
    push_to_session(session_id=session_id, event=SSEEvent.FINAL, data={"answer": answer + image_str})


def answer_question(state):
    func_name = sys._getframe().f_code.co_name
    logger.info(f"进入了函数{func_name}")
    add_running_task(state["task_id"], func_name, state["is_stream"])
    _is_stream = state.get("is_stream", False)
    # 1.检查state中的answer，如果有答案，说明回答不上来，没提取出对话中的实体，直接返回，如果没答案，继续下面步骤
    answer_exists = step1_check_answer_exists(state)

    if not answer_exists:
        # 2.提取state中的变量，生成prompt交给模型生成结果后润色输出
        llm_answer, _image_urls = step2_generate_prompt_to_llm(state)

        # answer存起来
        state["answer"] = llm_answer
        answer_user(session_id=state.get("session_id", ""), task_id=state.get("task_id", ""),
                    answer=llm_answer,
                    is_stream=_is_stream,
                    is_no_answer=False)

        # 3.保存回答到mongodb
        step3_save_llm_answer_message_to_mongodb(state, image_urls=_image_urls)

        if _is_stream:
            # 4.最后一次输出final_push  触发页面图片渲染的sse
            step4_output_answer(session_id=state.get("session_id", ""),
                                answer=llm_answer
                                )

    else:
        # 模型直接输出 跳步保存
        step3_save_llm_answer_message_to_mongodb(state, image_urls=[])
        # if _is_stream:
        #     # 4.最后一次输出final_push  触发页面图片渲染的sse
        #     step4_output_answer(session_id=state.get("session_id", ""),
        #                         answer=state["answer"]
        #                         )

    add_done_task(state["task_id"], func_name, state["is_stream"])

    # 整个流程结束（含 FINAL 已下发）后再清理任务并销毁 SSE 队列，避免提前 remove 导致 final 发不出去
    clear_task(session_id=state.get("session_id", ""), task_id=state.get("task_id", ""),
               status="completed", answer=state.get("answer", ""))

    logger.info(f"离开了函数{func_name}，当前状态为：{state}")


if __name__ == "__main__":
    mock_reranked_docs = [
        {
            "chunk_id": "local_101",
            "source": "local",
            "title": "HAK 180 烫金机操作手册_v2.pdf",
            "score": 0.95,
            "text": """
               HAK 180 烫金机的操作面板位于机器正前方。
               开启电源后，您需要先设置温度，默认建议设置在 110℃ 左右。
               具体的操作面板布局请参考下图：
               ![操作面板布局图](http://local-server/images/panel_view.jpg)

               如果是进行局部烫金，请调节侧面的旋钮。
               ![侧面旋钮细节](http://local-server/images/knob_detail.png)
               """
        },
        {
            "chunk_id": None,
            "source": "web",
            "title": "HAK 180 常见故障排除 - 官网",
            "score": 0.88,
            "url": "http://example.com/hak180_troubleshooting.jpeg",  # 这是一个直接指向图片的URL（虽然少见，但用于测试提取）
            "text": "如果机器无法加热，请检查保险丝是否熔断..."
        },
        {
            "chunk_id": "local_102",
            "source": "local",
            "title": "安全注意事项",
            "score": 0.82,
            "text": "操作时请务必佩戴隔热手套，避免高温烫伤。"
        }
    ]

    # 模拟历史记录
    mock_history = [
        {"role": "user", "text": "你好，这款机器怎么用？"},
        {"role": "assistant", "text": "您好！请问您具体指的是哪一款机器？"},
        {"role": "user", "text": "HAK 180 烫金机"}
    ]

    # 模拟输入状态
    mock_state = {
        "session_id": "test_answer_session_001",
        "original_query": "HAK 180 烫金机怎么操作？",
        "rewritten_query": "HAK 180 烫金机的具体操作步骤和面板设置方法",
        "item_names": ["HAK 180 烫金机"],
        "history": mock_history,
        "reranked_docs": mock_reranked_docs,
        "is_stream": False,  # 测试非流式
        # "is_stream": True, # 若要测试流式，需确保 SSE 环境或 mock 相关函数
        "answer": None  # 初始无答案
    }

    try:
        # 运行节点
        result = answer_question(mock_state)

        print("\n" + "=" * 50)
        print(">>> 测试结果摘要:")

        # 1. 验证 Prompt 构建
        # if "prompt" in result:
        #     print(f"[PASS] Prompt 构建成功 (长度: {len(result['prompt'])})")
        #     # print(f"Prompt 预览:\n{result['prompt'][:200]}...")
        # else:
        #     print("[FAIL] Prompt 未构建")
        #
        # # 2. 验证答案生成
        # answer = result.get("answer")
        # if answer and len(answer) > 10:
        #     print(f"[PASS] 答案生成成功 (长度: {len(answer)})")
        #     print(f"答案预览: {answer[:50]}...")
        # else:
        #     print(f"[WARN] 答案生成可能异常 (Content: {answer})")

        # 3. 验证图片提取
        # 我们期望提取到 3 张图片：
        # 1. http://local-server/images/panel_view.jpg (来自 local_101)
        # 2. http://local-server/images/knob_detail.png (来自 local_101)
        # 3. http://example.com/hak180_troubleshooting.jpeg (来自 web 结果的 url 字段)

        # 注意：这里我们没办法直接从 result state 里拿到 image_urls，因为它是作为 SSE 推送出去的，或者存库了
        # 但我们可以通过日志观察 _extract_images_from_docs 的输出
        # 如果需要验证，可以临时修改 node_answer_output 返回 image_urls
        print("\n[INFO] 请检查上方日志中是否包含 '图片提取完成' 及以下 URL:")
        print(" - http://local-server/images/panel_view.jpg")
        print(" - http://local-server/images/knob_detail.png")
        print(" - http://example.com/hak180_troubleshooting.jpeg")

        print("=" * 50)

    except Exception as e:
        logger.exception(f"测试运行期间发生未捕获异常: {e}")
