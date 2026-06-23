import json
import sys

from conf.llm_config import llm_config
from core.load_prompt import load_prompt
from core.logger import logger
from graph.import_process.state import ImportGraphState, create_default_state
from utils.llm_util import get_llm_client
from utils.path_util import PROJECT_ROOT
from utils.task_util import add_running_task

DEFAULT_ITEM_NAME_CHUNK_K = 5
# 单个切片内容截断长度：防止单切片内容过长，占满大模型上下文
SINGLE_CHUNK_CONTENT_MAX_LEN = 800

CONTEXT_TOTAL_MAX_CHARS = 2500
"""
    这个节点主要是为了识别md文档分块的实体名称,步骤有
    1.抽取file_title和抽取chunks提取前n个作为上下文传给模型，如果连file_title都没有，使用chunks第0个试试有没有有效的名称
    2.格式化chunk去除掉没用的字符,拼接成纯字符串  尽量拼接有用信息，减少token使用
    3.调用模型传入上下文识别出item_name加入到state
    4.使用稀疏模型和稠密模型为item_name生成向量
    5.将向量和对应的payload存入milvus

"""


def step2_format_chunk(chunks: list[dict], max_chunk_num: int = DEFAULT_ITEM_NAME_CHUNK_K,
                       max_item_chunk_len: int = SINGLE_CHUNK_CONTENT_MAX_LEN,
                       max_chunk_len: int = CONTEXT_TOTAL_MAX_CHARS,
                       ) -> str:
    """
    将文档切片整理成适合传给大模型识别实体名称的上下文字符串。

    处理逻辑：
    1. 优先取前 max_chunk_num 个 chunk/sub_chunk，避免上下文过长；
    2. 每个切片拼接标题和正文内容，保留最有助于识别商品名称的信息；
    3. 单个切片超过 max_item_chunk_len 时截断；
    4. 最终上下文超过 max_chunk_len 时再次截断。

    :param chunks: 文档切片列表，每个元素通常包含 title/content/sub_chunks 等字段
    :param max_chunk_num: 最多选取的切片数量
    :param max_item_chunk_len: 单个切片允许保留的最大字符数
    :param max_chunk_len: 最终上下文字符串允许保留的最大字符数
    :return: 拼接并截断后的上下文字符串
    """
    cur_chunk_num = 0
    final_chunk_list = []
    for chunk in chunks:

        if cur_chunk_num >= max_chunk_num:
            break

        if chunk["sub_chunks"]:
            # 有子chunk的
            for sub_chunk in chunk["sub_chunks"]:
                if cur_chunk_num >= max_chunk_num:
                    break
                else:
                    chunk_title_str = sub_chunk["title"].strip() if sub_chunk["title"] else chunk["title"].strip()
                    chunk_content_str = sub_chunk["content"].strip()
                    temp_str = f"标题 {chunk_title_str}\n内容 {chunk_content_str}"

                    # 先做单个的chunk
                    if len(temp_str) > max_item_chunk_len:
                        temp_str = temp_str[:max_item_chunk_len]

                    final_chunk_list.append(temp_str)
                    cur_chunk_num += 1

        else:
            # 没有子chunk的
            chunk_title_str = chunk["title"].strip()
            chunk_content_str = chunk["content"].strip()
            temp_str = f"标题 {chunk_title_str}\n内容 {chunk_content_str}"

            # 先做单个的chunk
            if len(temp_str) > max_item_chunk_len:
                temp_str = temp_str[:max_item_chunk_len]

            final_chunk_list.append(temp_str)
            cur_chunk_num += 1

    final_chunk_str = "\n".join(final_chunk_list)

    # 不能超过最大长度
    if len(final_chunk_str) > max_chunk_len:
        final_chunk_str = final_chunk_str[:max_chunk_len]

    return final_chunk_str


def step4_generate_embedding_for_item_name(item_name: str):
    """
    为识别出的实体名称生成向量表示。

    接入 BGE-M3  embedding 模型，生成实体名称对应的
    稠密向量和稀疏向量，用于写入 Milvus 后进行实体名称召回

    :param item_name: 大模型识别出的实体/商品名称
    :return: 实体名称对应的向量结果，具体格式由后续 embedding 实现决定
    """

    if not item_name:
        logger.warning("实体名称为空,返回空向量")
        return None, None


def step3_recognize_item_name_by_llm(file_title, chunks_str: str):
    """
    调用大模型，根据文件名和文档切片上下文识别实体/商品名称。

    处理逻辑：
    1. 初始化大模型客户端；
    2. 加载系统提示词和实体名称识别人类提示词；
    3. 将文件名与切片上下文填充进提示词模板；
    4. 调用大模型并返回识别结果。

    :param file_title: 当前文档标题或文件名，用作实体名称识别的重要线索
    :param chunks_str: 由文档切片拼接出的上下文字符串
    :return: 大模型识别出的实体/商品名称字符串
    """
    llm = get_llm_client(model=llm_config.lv_model)

    system_prompt = load_prompt("product_recognition_system", )
    logger.debug(f"系统提示词：{system_prompt}")
    human_prompt = load_prompt("item_name_recognition",
                               file_title=file_title,
                               context=chunks_str
                               )

    messages = [("system", system_prompt), ("human", human_prompt)]

    response = llm.invoke(messages)
    result = response.content

    return result


def step5_store_embedding_to_milvus(embeddings, item_name):
    """
    将实体名称及其向量结果写入 Milvus。

    当前函数暂未实现，后续可用于把 item_name、稠密向量、稀疏向量以及相关元数据
    持久化到 Milvus 集合中，便于后续实体名称检索、相似名称匹配或去重。

    :param embeddings: 实体名称对应的向量结果
    :param item_name: 需要写入 Milvus 的实体/商品名称
    :return: None
    """
    pass


def step1_get_node_params(state: ImportGraphState):
    """
    从导入流程状态中提取实体名称识别节点需要的基础参数。

    处理逻辑：
    1. 优先读取 state 中的 file_title 作为目标文件标题；
    2. 读取 state 中的 chunks 作为后续大模型识别上下文来源；
    3. 如果 file_title 为空，则尝试使用第一个 chunk 的标题作为兜底文件名。

    :param state: 导入流程状态对象，需包含 file_title 和 chunks 字段
    :return: 元组 (target_file_title, chunks)，分别表示目标文件标题和文档切片列表
    """
    file_title = state["file_title"]
    chunks = state["chunks"]

    target_file_title = file_title if file_title else ""

    if not target_file_title and chunks[0]:
        target_file_title = chunks[0]["title"] or "无文件名文件"

    return target_file_title, chunks


def node_item_name_recognition(state: ImportGraphState):
    """
    实体名称识别节点入口函数。

    节点职责：
    1. 从 state 中提取文件标题和文档切片；
    2. 将前若干个文档切片格式化为大模型可读的上下文；
    3. 调用大模型识别当前文档对应的实体/商品名称；
    4. 将识别结果写回 state["item_name"]；
    5. 预留实体名称向量生成与 Milvus 入库步骤。

    :param state: 导入流程状态对象
    :return: 当前节点处理后的 state
    """
    func_name = sys._getframe().f_code.co_name
    add_running_task(state["task_id"], func_name)

    logger.info(f"进入了函数{func_name}")

    file_title, _chunks = step1_get_node_params(state=state)

    chunks_str = step2_format_chunk(chunks=_chunks)

    item_name = step3_recognize_item_name_by_llm(file_title, chunks_str)
    logger.info(f"识别出的实体名称为：{item_name}")

    # 使用文件名作为实体名称兜底
    if not item_name:
        logger.warning(f"没有识别出实体名称，使用文件名作为实体名称兜底")
        item_name = file_title

    state["item_name"] = item_name

    # 把识别出的实体名称写入 chunk，顺便补齐其他空值字段，为了和子字段一样
    _chunks = [
        {**chunk, "item_name": item_name, "parent_title": chunk.get("parent_title", ""), "part": chunk.get("part", 0)}
        for chunk in _chunks]
    state["chunks"] = _chunks

    embeddings = step4_generate_embedding_for_item_name(item_name)

    step5_store_embedding_to_milvus(embeddings, item_name)

    logger.info(f"离开了函数{func_name}，state状态为：{state}")

    return state


if __name__ == '__main__':
    chunks_path = PROJECT_ROOT / "output" / "111" / "chunk.json"
    chunks = None
    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    state = create_default_state(
        chunks=chunks,
        file_title="111",
    )

    node_item_name_recognition(state=state)
