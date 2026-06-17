import copy
import re
import shutil
from pathlib import Path

from langchain_core.messages import HumanMessage

from conf.llm_config import llm_config
from core.logger import logger
from graph.import_process.state import ImportGraphState, create_default_state
from utils.llm_util import get_llm_client
from utils.minio_util import batch_upload_to_minio, is_minio_avilable
from utils.other import get_current_func_name
from utils.path_util import PROJECT_ROOT
from core.load_prompt import load_prompt

"""
    该节点实现的功能是将本地存储的md文档上传到minio，转换成在线md文档(如果不用minio那就把本地图片转成base64格式)
    然后交给多模态大模型分析语义,因为厂商有限制上传速率，这里得做一下限速
    分步骤
    
    1.解析参数并校验
    2.用md文档匹配同级images文件夹看引用了那些图片
    3.构造数据传给minio,拿返回的url替换md文档中的本地图片
    4.把md文档传给视觉大模型分析，总结摘要
    5.更新对应的state参数 taskid md_path,md_content
    
    tip：如果没有图片 跳过所有步骤
"""


def step1_get_node_params(state: ImportGraphState) -> tuple:
    """
    获取节点要用到的参数，顺带校验
    :param state:
    :return: 返回path类型的md文件地址和md文件内容
    """

    md_path = state["md_path"]
    md_content = state["md_content"]
    md_path_obj = Path(md_path)

    # 校验md文件地址
    if not md_path or not md_path_obj.exists():
        logger.error(f"文件参数不存在/文件不存在,请检查文件路径是否正确{md_path}")
        raise FileNotFoundError(f"文件参数不存在/文件不存在,请检查文件路径是否正确{md_path}")

    # 校验md内容，没有就再去读一次
    if not md_content:
        with open(md_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()

    return md_path_obj, md_content


def step2_get_real_md_img_path(md_content: str, md_images_dir: Path) -> list:
    """
    过滤出所有要上传的图片
    :param md_content:
    :param md_images_dir:
    :return:
    """

    files = md_images_dir.rglob("*")
    list = []
    for file in files:
        if file.name in md_content:
            list.append(file)
    return list


def find_img_context(md_content: str, img_name: str, context_len=100):
    "获取图片所在内容上下文"
    pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(img_name) + r".*?\)")
    results = []
    pre_text = ''
    post_text = ''
    _md_content = md_content.strip().replace("\n", "")
    # 迭代查找所有MD图片标签匹配项
    for m in pattern.finditer(_md_content):
        start, end = m.span()  # 返回开始和结束的索引  是个元组
        # 截取匹配位置的上文和下文（防止索引越界）
        pre_text = _md_content[max(0, start - context_len):start]
        post_text = _md_content[end:min(len(_md_content), end + context_len)]

    return (pre_text, post_text)


def step4_analysis_md_img(md_name: str, online_urls_map: dict) -> dict:
    """
    把图片和图片所在上下文截取发给模型写摘要
    :param online_urls_map:
    :return:
    """
    summary_and_urls_map = copy.deepcopy(online_urls_map)

    for img_name, image_info in summary_and_urls_map.items():
        prompt_content = load_prompt("image_summary",
                                     root_folder=md_name,
                                     image_content=image_info["context"]
                                     )

        llm = get_llm_client(model=llm_config.lv_model)

        # 2. 构造LangChain标准多模态HumanMessage（兼容千问/OpenAI等视觉模型）
        messages = [
            HumanMessage(
                content=[
                    # 文本提示词：携带上下文，限定摘要规则
                    {
                        "type": "text",
                        "text": prompt_content
                    },
                    # 多模态核心：Base64编码图片数据
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_info["online_path"]
                        }
                    }

                ]
            )
        ]

        result = llm.invoke(messages)
        print(result.content)

        image_info["summary"] = result.content

    return summary_and_urls_map


def step5_replace_md_img_content(md_content, analysis_md_img_result: dict):
    """
    用正则匹配替换掉简介和图片地址
    :param md_content: 
    :param analysis_md_img_result: 
    :return: 
    """
    _md_content = md_content
    for local_img_name, img_info in analysis_md_img_result.items():
        _md_content = re.sub(fr"!\[([^\]]*)\]\((images/{Path(local_img_name).name})\)",
                             fr"![{img_info['summary']}]({img_info['online_path']})", _md_content)

    return _md_content


def step6_backup_md_file(origin_md_path_obj: Path, new_md_content: str):
    # 备份并且创建一个新文件写入

    new_md_path = origin_md_path_obj.parents[0] / f"{origin_md_path_obj.stem}_new.md"

    if new_md_path.exists():
        new_md_path.unlink()

    with open(new_md_path, "w", encoding="utf-8") as f:
        f.write(new_md_content)


def node_analysis_md_img(state: ImportGraphState):
    current_func_name = get_current_func_name()
    logger.info(f"进入了函数{current_func_name}")

    md_path_obj, md_content = step1_get_node_params(state)
    # md图片目录
    md_images_dir = md_path_obj.parents[0] / "images"

    if not md_images_dir.exists() or not md_images_dir.rglob("*"):
        logger.warning(f"没有图片目录，跳过图片处理")
        return state

    # 准备图片路径
    prepare_img_path = step2_get_real_md_img_path(md_content=md_content, md_images_dir=md_images_dir)

    # 上传图片到minio,获取映射
    flag = is_minio_avilable()
    logger.info(f"minio服务可用性{flag}")
    if not flag:
        logger.warning(f"minio服务不可用，请检查minio服务是否正常")
        # return state

    online_urls_map = batch_upload_to_minio(prepare_img_path)

    # 用键值对格式
    online_urls_map = {
        img_name: {"online_path": online_path, "summary": '',
                   "context": find_img_context(md_content=md_content, img_name=Path(img_name).name)}
        for img_name, online_path in online_urls_map.items()
    }

    # 把图片交给视觉模型分析，生成摘要，过滤失败图片
    summary_and_urls_map = step4_analysis_md_img(md_name=md_path_obj.stem, online_urls_map=online_urls_map)

    # 用摘要和图片替换md_content中的内容并且新建一个本地文件
    # 图片示例
    # ![](images / 048c005b198be5c9fff80ad6a6ba02496f38fa109ec20dbaabde3110f3eb1574.jpg)

    final_md_content = step5_replace_md_img_content(md_content, summary_and_urls_map)
    logger.info(f"替换后的md_content：{final_md_content}")

    state["md_content"] = final_md_content

    # 备份md_content文件到本地
    step6_backup_md_file(origin_md_path_obj=md_path_obj, new_md_content=final_md_content)

    logger.info(f"离开了函数{current_func_name}")

    return state


if __name__ == '__main__':
    """ 
    测试代码
    """

    md_file = Path(PROJECT_ROOT) / "output" / "111" / "111.md"

    md_content = ""
    with open(md_file, "r", encoding="utf-8") as f:
        md_content = f.read()

    state = create_default_state(is_md_read_enable=True, file_title=md_file.name,
                                 md_content=md_content,
                                 md_path=str(md_file),
                                 )
    logger.info(state)
    node_analysis_md_img(state)
