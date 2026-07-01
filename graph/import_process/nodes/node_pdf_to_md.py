import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Callable

import requests
import os

from dotenv import load_dotenv, find_dotenv

from core.logger import logger
from graph.import_process.state import ImportGraphState, create_default_state

from utils.path_util import PROJECT_ROOT
from utils.task_util import add_running_task

load_dotenv(find_dotenv())


def step1_upload_to_mineru(state: ImportGraphState) -> str:
    # 上传至mineru返回获取进度的batch_id 地址
    token = os.getenv("MINERU_API_TOKEN")
    base_url = os.getenv("MINERU_BASE_URL")
    upload_info = None  # 上传pdf地址及查询状态信息
    batch_id = ""  # 获取进度的batch_id
    file_title = state["file_title"]
    pdf_path = state["pdf_path"]

    # 校验需要的参数
    if not file_title:
        logger.error(f"文件名参数错误")

    if not pdf_path or not Path(pdf_path).exists():
        logger.error(f"文件不存在,请检查文件路径是否正确")

    url = f"{base_url}/file-urls/batch"
    header = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "files": [
            {"name": f"{file_title}", }
        ],
        "model_version": "vlm"
    }
    file_path = [f"{pdf_path}"]

    # 上传
    try:
        response = requests.post(url, headers=header, json=data)
        if response.status_code == 200 and response.json()["code"] == 0:
            # 对象转json
            upload_info = response.json()["data"]

            # 防止开代理后乱加请求头
            http_session = requests.Session()
            http_session.trust_env = False

            try:
                with open(pdf_path, 'rb') as f:
                    res_upload = http_session.put(upload_info["file_urls"][0], data=f)
                    if res_upload.status_code == 200:
                        logger.info(f"文件{file_title} 上传成功,状态f{res_upload}")
                        batch_id = upload_info["batch_id"]
                    else:
                        logger.info(f"文件{file_title} 上传失败，状态f{res_upload.status_code}")
            except Exception as e:
                logger.error(f"上传失败，请检查文件路径是否正确,错误信息{str(e)}")
            finally:
                http_session.close()

        else:

            logger.error(f"获取上传路径失败,状态码为{response.status_code},错误信息为{response.content}")

    except Exception as err:
        logger.error(f"获取上传路径失败,错误信息{str(err)}")
    return batch_id


def step2_get_progress(state: ImportGraphState, batch_id: str,
                       on_success: Callable[[ImportGraphState, str], None] | None):
    # zip_upload_url = ""  # zip下载地址
    interval = 5
    timeout_seconds = 600  # 超时秒数
    start_time = time.time()
    token = os.getenv("MINERU_API_TOKEN")
    base_url = os.getenv("MINERU_BASE_URL")
    url = f"{base_url}/extract-results/batch/{batch_id}"
    header = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # 轮询获取下载结果
    while True:
        if time.time() - start_time > timeout_seconds:
            logger.error(f"获取pdf文件解析进度超时，已轮询 {timeout_seconds} 秒")
            raise TimeoutError(f"获取pdf文件解析进度超时")

        time.sleep(interval)

        try:
            res = requests.get(url, headers=header, timeout=10)
            logger.info(f"轮询 MinerU 进度，batch_id: {batch_id}, 状态码: {res.status_code}")

            if res.status_code == 200:
                res_data = res.json()
                logger.info(f"MinerU 返回数据: {res_data}")

                if res_data.get("code") == 0:
                    try:
                        result = res_data["data"]["extract_result"]

                        if result and len(result) > 0:
                            current_state = result[0].get("state", "unknown")
                            logger.info(f"MinerU 当前状态: {current_state}")

                            if current_state == "done":
                                full_zip_url = result[0].get("full_zip_url")
                                logger.info(f"获取pdf文件解析进度成功，下载地址: {full_zip_url}")

                                # 回调执行下一步
                                if on_success:
                                    on_success(state, full_zip_url)

                                break
                            elif current_state == "failed":
                                err_msg = result[0].get("err_msg", "未知错误")
                                logger.error(f"MinerU 处理文件失败: {err_msg}")
                                raise RuntimeError(f"MinerU 处理文件失败: {err_msg}")
                            else:
                                logger.info(f"MinerU 处理中，当前状态: {current_state}，继续轮询...")
                        else:
                            logger.warning(f"MinerU 返回结果为空，继续轮询...")

                    except KeyError as e:
                        logger.error(f"解析 MinerU 响应数据失败，缺少字段: {e}，继续轮询...")
                    except Exception as e:
                        logger.error(f"处理 MinerU 响应失败: {e}，继续轮询...")
                else:
                    logger.warning(f"MinerU 返回 code 非 0: {res_data.get('code')}，消息: {res_data.get('message')}，继续轮询...")
            else:
                logger.warning(f"MinerU API 返回非 200 状态码: {res.status_code}，响应: {res.text[:200]}，继续轮询...")

        except requests.exceptions.Timeout:
            logger.warning(f"请求 MinerU 超时，继续轮询...")
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 MinerU 失败: {e}，继续轮询...")
        except Exception as e:
            logger.error(f"轮询过程中发生未知错误: {e}，继续轮询...")


def step3_upload_zip_to_local(state: ImportGraphState, zip_upload_url: str):
    print("开始执行下载zip文件到本地解压成md文件，文件地址为:", zip_upload_url)

    response = requests.get(zip_upload_url)
    local_dir = state["local_dir"]
    md_path = ''
    local_dir_obj = Path(local_dir)
    file_title = state["file_title"]
    extract_zip_dir = local_dir_obj / file_title  # md文件夹解压路径
    md_target_path_str = str(extract_zip_dir / f"{file_title}.md")  # 最终的md文件保存路径

    zip_save_path = local_dir_obj / f"{file_title}_result.zip"
    if response.status_code == 200:
        logger.info(f"下载zip文件成功,即将保存zip文件到本地")
        with open(zip_save_path, "wb") as f:
            f.write(response.content)
        logger.info(f"保存zip文件到本地,保存路径为{zip_save_path}")

        if extract_zip_dir.exists():
            shutil.rmtree(extract_zip_dir)

        # 解压zip到同名文件夹
        with zipfile.ZipFile(zip_save_path, "r") as zip_file_object:
            zip_file_object.extractall(extract_zip_dir)
        logger.info(f"文件解压成功,保存路径为{extract_zip_dir}")

        # 找到文件夹下的md文件，改名为文件夹名.md
        md_list = extract_zip_dir.rglob("*.md")
        md_list = list(md_list)
        target_name = extract_zip_dir.stem + ".md"
        if md_list:
            if md_list[0].name != target_name:
                target_md_file = md_list[0]
                # 进行重命名
                # target_md_file.with_name(f"{stem}.md") 修改path对象 （不涉及文件操作） 返回结果是修改后path对象
                # target_md_file.rename(target_md_file.with_name(f"{stem}.md")) 修改磁盘中的文件名称（修改名称了） return 新的路径path

                target_md_file.rename(target_md_file.with_name(target_name))
                logger.info(f"文件名为{target_name}")

            else:
                logger.info(f"文件夹同名md文件已存在，无需处理")

            # 这时候有md文件就是想要的文件路径
            md_path = target_name
        else:
            logger.error(f"未找到md文件")
            raise RuntimeWarning(f"mineru上传完下载，解压后未找到md文件")

    logger.info(f"zip文件的md文档解压成功,保存路径为{md_target_path_str}")
    if md_path:
        state["md_path"] = md_target_path_str

    if md_target_path_str:
        md_content = ''
        with open(md_target_path_str, "r", encoding="utf-8") as f:
            md_content = f.read()

        state["md_content"] = md_content


def node_pdf_to_md(state: ImportGraphState):
    """
        当前节点做的事，主要是pdf转md,划分步骤
        1.拿到pdf文件路径，传给mineru,轮训拿到结果，结果是zip
        2.get下载到本地后，用zipfile解压到同名文件夹
        3.兼容md文档是xxx.md或者full.md或者其他.md,统一成主体名.md

        (不用sdk，因为会报错且不能批量传)
    """

    func_name = sys._getframe().f_code.co_name
    add_running_task(state["task_id"], func_name)
    logger.info(f"进入了节点{func_name}")

    try:
        batch_id = step1_upload_to_mineru(state)

        if batch_id:
            step2_get_progress(state, batch_id=batch_id,
                               on_success=lambda state, full_zip_url: step3_upload_zip_to_local(state, full_zip_url))
        else:
            logger.error(f"上传到 MinerU 失败，未获取到 batch_id")
            raise RuntimeError("上传到 MinerU 失败")

        logger.info(f"离开了函数{func_name}，state状态{state}")

    except (TimeoutError, RuntimeError) as e:
        # MinerU 处理超时或失败，记录错误并抛出异常，停止图执行
        logger.error(f"MinerU 处理失败: {e}")
        add_done_task(state["task_id"], func_name)  # 标记当前节点完成（虽然失败了）
        raise  # 重新抛出异常，让图执行停止

    return state


if __name__ == '__main__':
    """
    测试代码
    """
    state = create_default_state(is_pdf_read_enable=True, file_title="111",
                                 pdf_path=str(Path(PROJECT_ROOT) / "doc" / "hak180产品安全手册.pdf"),
                                 local_dir=Path(PROJECT_ROOT) / "output")

    node_pdf_to_md(state)
