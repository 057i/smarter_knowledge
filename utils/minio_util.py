import json
from pathlib import Path

from minio import Minio

from conf.minio_config import minio_config
from core.logger import logger

# 全局minio单例模式
minio_client = None

# 桶名称
bucket_name = minio_config.bucket_name


def is_minio_avilable() -> bool:
    """
    判断minio服务是否可用
    :return:
    """
    temp = True if minio_client else False
    return temp


def list_buckets() -> list:
    """
    列出可用桶信息
    :return:
    """
    buckets = minio_client.list_buckets()
    return buckets


def bucket_exists(bucket_name: str) -> bool:
    """
    判断桶是否存在
    :return:
    """
    return minio_client.bucket_exists(bucket_name)


def set_bucket_policy():
    """配置用户可以通过url访问桶内文件"""
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},  # *表示所有匿名用户（S3兼容标识）
            "Action": ["s3:GetObject"],  # 仅授权文件获取/访问操作
            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
        }]
    }
    minio_client.set_bucket_policy(bucket_name, json.dumps(bucket_policy))
    logger.info(f"minio存储桶[{bucket_name}]已配置公网只读策略，支持匿名URL访问")


def batch_upload_to_minio(file_paths: list[Path] = None) -> dict[str, str]:
    """
        批量上传文件到minio
        :param
        :file_paths 文件路径列表
        :return  返回url列表
    """
    logger.info(f"开始批量上传文件到minio")
    try:
        urls_map = {str(file_path).replace("\\", "/"): upload_to_minio(file_path) for file_path in file_paths}
        return urls_map

    except Exception as e:
        logger.error(f"批量上传文件到minio失败{e}")
        raise f"批量上传文件到minio失败{e}"


def upload_to_minio(file_path: Path = None) -> str:
    """
        上传单个文件到minio，用流传 避免大文件
        :param
        :file_path 文件路径
        :return  返回url路径
    """
    try:
        real_suffix = file_path.suffix[1:]
        content_type_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
        }

        content_type = content_type_map[real_suffix] or content_type_map["jpg"]

        logger.info(f"开始上传文件到minio{content_type}")

        minio_client.fput_object(
            bucket_name=bucket_name,
            object_name=file_path.name,
            file_path=str(file_path),
            content_type=content_type,  # 不加或者加错会变成下载
        )
        # 拼接url
        file_url = f"{'https' if minio_config.minio_secure else 'http'}://{minio_config.endpoint}/{bucket_name}/{file_path.name}"
        return file_url
    except Exception as e:
        logger.error(f"上传文件到minio失败{e}")
        raise f"上传文件到minio失败{e}"


try:
    logger.info("执行minio初始化")
    minio_client = Minio(
        minio_config.endpoint,
        access_key=minio_config.access_key,
        secret_key=minio_config.secret_key,
        secure=minio_config.minio_secure
    )
    set_bucket_policy()

    logger.info(f"minio初始化成功")


except Exception as e:
    logger.error(f"minio初始化失败{e}")
    minio_client = None
