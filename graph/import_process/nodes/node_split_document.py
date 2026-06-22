import copy
import json
import re
import sys

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.logger import logger
from graph.import_process.state import ImportGraphState, create_default_state
from utils.other import get_current_func_name
from utils.path_util import PROJECT_ROOT

"""
这个节点主要做的是将md_content中的内容切分，步骤有
1.提取改节点要用到的参数
2.按md文档1-6级标题切分若干块，进行第一轮粗切
3.遍历一次粗切的大块变小块
4.遍历全部的块，如果是同一个大块下的小块切太小了合并，如果不是同一个大块，在文中的位置差太远了没有合并的必要
"""
# --- 配置参数 (Configuration) ---
# 单个Chunk最大字符长度：超过则触发二次切分（适配大模型上下文窗口）
DEFAULT_MAX_CONTENT_LENGTH: int = 200
# 短Chunk合并阈值：同父标题的短Chunk会被合并，减少碎片化
MIN_CONTENT_LENGTH: int = 50


def step1_get_node_params(state: ImportGraphState) -> tuple[str, str]:
    md_content = state["md_content"]
    file_title = state["file_title"]
    # 统一处理不同系统换行符
    md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
    return md_content, file_title


def step2_split_document_by_title(content: str, file_title: str) -> list[dict]:
    # 兼容空标题行：## 后面无文字也识别为标题
    title_pattern = r'^\s*#{1,6}\s*.*'

    lines = content.split("\n")
    is_code_block_flag = False
    current_title = ""
    sessions = []
    current_lines = []

    def _flush_section():
        if not current_lines:
            return
        sessions.append({
            "file_title": file_title,
            "title": current_title,
            "content": "\n".join(current_lines),
            "sub_chunks": []  # 提前初始化子块列表，避免KeyError
        })

    for line in lines:
        striped_line = line.strip()

        # 空行保留到文本，不直接跳过（保留文档格式）
        if not striped_line:
            current_lines.append(line)
            continue

        # 切换代码块标记，不丢弃代码行
        if striped_line.startswith("```"):
            is_code_block_flag = not is_code_block_flag
            current_lines.append(line)
            continue

        # 非代码块内识别标题
        if not is_code_block_flag and re.fullmatch(title_pattern, line):
            _flush_section()
            current_title = line
            current_lines = [line]
        else:
            current_lines.append(line)
    # 刷新最后一段
    _flush_section()
    return sessions


def step3_handle_no_title_sessions(sessions: list[dict]) -> list[dict]:
    current_sessions = copy.deepcopy(sessions)
    # 通篇无标题，统一赋值默认标题
    if len(current_sessions) == 1 and not current_sessions[0]["title"].strip():
        current_sessions[0]["title"] = "# 无标题文档内容"
    return current_sessions


def split_long_chunk(sessions: list[dict]) -> list[dict]:
    current_sessions = copy.deepcopy(sessions)
    max_chunk_len = DEFAULT_MAX_CONTENT_LENGTH
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_len,
        chunk_overlap=0,
        separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " ", ""],
    )

    for session in current_sessions:
        content = session["content"]

        if len(content) >= max_chunk_len:
            sub_texts = splitter.split_text(content)
        else:
            sub_texts = [content]

        sub_list = []
        for idx, sub_text in enumerate(sub_texts):
            sub_list.append({
                "title": f"{session['title']} 第{idx + 1}小块",
                "content": sub_text,
                "part": idx + 1,
                "parent_title": session["title"],
                "file_title": session["file_title"]
            })

        session["sub_chunks"] = sub_list

    return current_sessions


def merge_short_chunk(sessions: list[dict]) -> list[dict]:
    current_sessions = copy.deepcopy(sessions)
    min_len = MIN_CONTENT_LENGTH
    max_len = DEFAULT_MAX_CONTENT_LENGTH

    for session in current_sessions:
        subs = session["sub_chunks"]
        if len(subs) <= 1:
            continue

        i = 0
        while i < len(subs) - 1:
            curr_text = subs[i]["content"]
            next_text = subs[i + 1]["content"]

            if (
                    len(curr_text) < min_len
                    and len(curr_text) + len(next_text) <= max_len
            ):
                subs[i]["content"] += f"\n{next_text}"
                subs.pop(i + 1)
            else:
                i += 1

    return current_sessions


def step4_refine_chunks(sessions: list[dict]) -> list[dict]:
    current_sessions = split_long_chunk(sessions)
    current_sessions = merge_short_chunk(current_sessions)
    return current_sessions


def node_split_document(state: ImportGraphState) -> ImportGraphState:
    func_name = get_current_func_name()
    logger.info(f"进入节点函数: {func_name}")

    md_content, file_title = step1_get_node_params(state)
    raw_sessions = step2_split_document_by_title(md_content, file_title)
    handled_sessions = step3_handle_no_title_sessions(raw_sessions)
    final_chunks = step4_refine_chunks(handled_sessions)

    # 切分结果回写到state，供下游节点使用
    # state["document_chunks"] = final_chunks
    logger.info(f"节点{func_name}执行完成，生成粗分段数：{len(final_chunks)}")
    for chunk in final_chunks:
        if chunk["sub_chunks"]:
            logger.info(f"分块 {chunk['title']} {len(chunk['sub_chunks'])}  {chunk['sub_chunks']}")
        else:
            logger.info(f" 不分块{chunk['title']}  {chunk['content']}")
    logger.info(final_chunks)
    state["chunks"] = final_chunks

    save_chunk_dir = PROJECT_ROOT / "output" / "111" / "chunk.json"

    with open(save_chunk_dir, "w", encoding="utf-8") as f:
        json.dump(
            final_chunks,
            f,
            indent=2,
            ensure_ascii=False
        )
    logger.info(f"离开了函数{func_name}，state状态为：{state}")

    return state


if __name__ == '__main__':
    from pathlib import Path

    file_path: Path = PROJECT_ROOT / "output" / "111" / "111.md"
    md_content = file_path.read_text(encoding="utf-8")
    file_title = file_path.stem
    state = create_default_state(
        file_title=file_title,
        md_content=md_content,
        file_path=file_path,
    )
    out_state = node_split_document(state)
