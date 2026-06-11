import json
import shutil
import sys
import time
import zipfile
from faulthandler import is_enabled
from pathlib import Path
from typing import Callable

import requests
import os
from core.logger import logger
from graph.state import ImportGraphState, create_default_state
from dotenv import load_dotenv, find_dotenv

from utils.path_util import PROJECT_ROOT

load_dotenv(find_dotenv())


def step1_upload_to_mineru(state: ImportGraphState) -> str:
    # 上传至mineru返回获取进度的batch_id 地址
    token = os.getenv("MINERU_API_TOKEN")
    base_url = os.getenv("MINERU_BASE_URL")
    upload_info = None  # 上传pdf地址及查询状态信息
    batch_id = ""  # 获取进度的batch_id
    file_title = state["file_title"]
    pdf_path = state["pdf_path"]

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
            logger.info(f"上传信息{upload_info}")

            # 防止开代理后乱加请求头
            http_session = requests.Session()
            http_session.trust_env = False

            try:
                with open(pdf_path, 'rb') as f:
                    res_upload = http_session.put(upload_info["file_urls"][0], data=f)
                    print(f"{res_upload.content}")
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

            logger.error(f"获取上传路径失败,状态码为{response.status_code}")

    except Exception as err:
        logger.error(f"获取上传路径失败,错误信息{str(err)}")
    return batch_id


def step2_get_progress(state: ImportGraphState, batch_id: str,
                       on_success: Callable[[ImportGraphState, str], None] | None):
    zip_upload_url = ""  # zip下载地址
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
    while True:
        if time.time() - start_time > timeout_seconds:
            logger.error(f"获取pdf文件解析进度超时")
            raise TimeoutError(f"获取pdf文件解析进度超时")
        time.sleep(interval)
        res = requests.get(url, headers=header)

        if res.status_code == 200 and res.json()["code"] == 0:
            try:
                result = res.json()["data"]["extract_result"]
                if result and result[0]["state"] == "done":
                    logger.info(f"获取pdf文件解析进度成功,进度为{result[0]["full_zip_url"]}")
                    if on_success:
                        on_success(state, result[0]["full_zip_url"])

                    break


            # return res.json()["data"]["full_zip_url"]
            except Exception as e:
                logger.error(f"获取pdf文件解析进度失败,错误信息{str(e)}")
                break


def step3_upload_zip_to_local(state: ImportGraphState, zip_upload_url: str):
    print("进入step3", zip_upload_url, state)

    response = requests.get(zip_upload_url)
    local_dir = state["local_dir"]

    local_dir_obj = Path(local_dir)
    file_title = state["file_title"]
    zip_save_path = local_dir_obj / f"{file_title}_result.zip"
    if response.status_code == 200:
        with open(zip_save_path, "wb") as f:
            f.write(response.content)
        logger.info(f"保存文件成功,保存路径为{zip_save_path}")

        extract_zip_dir = local_dir_obj / file_title
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
                logger.info(f"文件名解压成功,保存路径为{target_name}")

            else:
                logger.info(f"文件夹同名md文件已存在，无需处理")

        else:
            logger.error(f"未找到md文件")


def node_pdf_to_md(state: ImportGraphState):
    """
        当前节点做的事，主要是pdf转md,划分步骤
        1.拿到pdf文件路径，传给mineru,轮训拿到结果，结果是zip
        2.get下载到本地后，用zipfile解压到同名文件夹
        3.兼容md文档是xxx.md或者full.md或者其他.md,统一成主体名.md

        (不用sdk，因为会报错且不能批量传)
    """

    logger.info(f"进入了节点{sys._getframe().f_code.co_name}")
    batch_id = step1_upload_to_mineru(state)

    if batch_id:
        step2_get_progress(state, batch_id=batch_id,
                           on_success=lambda state, full_zip_url: step3_upload_zip_to_local(state, full_zip_url))
    logger.info(f"离开了函数{sys._getframe().f_code.co_name}")


state = create_default_state(is_pdf_read_enable=True, file_title="111",
                             pdf_path="../../doc/Aolynk CC系列室内型Cable网络集中器 用户手册-6W202-整本手册.pdf",
                             local_dir=Path(PROJECT_ROOT) / "output")

node_pdf_to_md(state)
