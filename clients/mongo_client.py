import datetime
import os

from bson import ObjectId
from pymongo import MongoClient

from core.logger import logger

_mongo_client = None


class MongoClientClass:
    def __init__(self):
        """
        类初始化方法：完成MongoDB的连接、数据库/集合获取、索引创建
        初始化失败会抛出异常并记录错误日志，确保程序感知连接问题
        """
        try:
            # 从环境变量读取MongoDB连接地址（敏感配置，不硬编码）
            self.mongo_url = os.getenv("MONGO_URL")
            # 从环境变量读取要使用的数据库名称
            self.db_name = os.getenv("MONGO_DB_NAME")

            # 创建MongoDB客户端实例，建立与数据库的连接
            self.client = MongoClient(self.mongo_url)
            # 获取指定名称的数据库对象
            self.db = self.client[self.db_name]
            # 获取对话记录的集合
            self.chat_messages = self.db["chat_messages"]

            # 为chat_message集合创建复合索引，提升查询性能
            # 索引规则：session_id升序 + ts降序，适配"按会话查最新记录"的核心查询场景
            # create_index索引已存在时不会重复创建，无需额外判断
            self.chat_messages.create_index([("session_id", 1), ("ts", -1)])
            # 记录成功日志，确认数据库连接和初始化完成
            logger.info(f"Successfully connected to MongoDB: {self.db_name}")
        except Exception as e:
            # 捕获所有初始化异常，记录详细错误日志
            logger.error(f"连接mongo失败: {e}")
            # 重新抛出异常，让调用方感知初始化失败，避免使用未初始化的实例
            raise RuntimeError("连接mongo失败")


def get_mongo_client():
    """
    获取MongoDB客户端实例
    :return: MongoDB客户端实例
    """
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClientClass()
    return _mongo_client


def delete_messages_by_session_id(session_id: str):
    """
    根据会话ID删除所有消息记录
    :param session_id: 会话ID
    :return: 删除的记录数
    """
    try:
        mongo_client = get_mongo_client()

        # 语法第一个字典是筛选条件，第二个字典是操作
        res = mongo_client.chat_messages.delete_many({
            "session_id": session_id
        })

        logger.info(f"删除消息记录成功，删除条数 {res.deleted_count}")
    except Exception as e:
        logger.error(f"删除消息记录失败: {e}")


def add_message(session_id: str = "",
                role: str = "",
                text: str = "",
                rewritten_query: str = "",
                task_id: str = "",
                image_urls: list = [],
                item_names: list[str] | None = None,
                message_id: str | None = None):
    """
    添加一条消息记录
    :param task_id:
    :param image_urls:
    :param session_id: 会话ID
    :param role: 消息角色
    :param text: 消息内容
    :param rewritten_query: 重写后的查询语句
    :param item_names: 关联的实体名称列表
    :param message_id: 消息ID
    :return: 添加的记录ID
    """
    try:
        mongo_client = get_mongo_client()
        content = {
            "role": role,
            "text": text,
            "rewritten_query": rewritten_query,
            "item_names": item_names,
            "session_id": session_id,
            "task_id": task_id,
            "image_urls": image_urls,
            "ts": datetime.datetime.now().timestamp()
        }
        content = {content_item_name: content_item_value if content_item_value else None
                   for content_item_name, content_item_value in content.items()}

        logger.info(f"{content}")

        if message_id:
            res = mongo_client.chat_messages.update_one({
                # mongodb默认主键类型为ObjectId
                "_id": ObjectId(message_id)
            }, {
                "$set": {
                    **content
                }
            })
            # __insert_or_update_id = str(res.insertedId)
            logger.info(f"更新消息记录成功，修改条数 {res.modified_count}")
            return res.modified_count
        else:

            res = mongo_client.chat_messages.insert_one({
                **content
            })
            inserted_id = str(res.inserted_id)
            logger.info(f"添加消息记录成功: {inserted_id}")
            return inserted_id

    except Exception as e:
        logger.error(f"添加消息记录失败: {e}")


def get_messages_by_session_id(session_id: str, limit: int = 10):
    """
    根据会话ID获取指定条消息记录
    :param limit: 返回消息数量上限（默认 10）
    :param session_id: 会话ID
    :return: 消息记录列表（按时间正序，从旧到新）
    """
    try:
        mongo_client = get_mongo_client()

        # 参数校验
        if limit <= 0:
            limit = 10

        # find返回的是一个cursor游标，需要将其转换为列表
        # 按时间倒序取最新 N 条，然后反转成正序（旧→新）
        cursor = mongo_client.chat_messages.find({
            "session_id": session_id
        }).sort([("ts", -1)]).limit(limit)

        messages = []
        for message in cursor:
            # 安全处理 _id 字段
            msg_id = message.get("_id")
            if not msg_id:
                logger.warning(f"消息记录缺少 _id 字段：{message}")
                continue

            temp_message = {
                **message,
                "id": str(msg_id)
            }
            del temp_message["_id"]
            messages.append(temp_message)

        # 反转成正序（从旧到新，符合对话流）
        messages.reverse()
        return messages

    except Exception as e:
        logger.error(f"获取消息记录失败: {e}")
        return []  # 返回空列表而不是 None，避免调用方报错


def update_message_item_names_by_id(ids: list[str], item_names: list[str]) -> int:
    """
    根据消息ID更新关联的实体名称列表
    :param ids: 消息主键
    :param item_names: 关联的实体名称列表
    :return: 更新的记录数
    """
    try:
        mongo_client = get_mongo_client()
        # 坑: mongodb默认主键类型为ObjectId, 因此需要将传入的ID转换为ObjectId类型
        object_ids = [ObjectId(_id) for _id in ids]
        res = mongo_client.chat_messages.update_many({
            "_id": {
                "$in": object_ids
            }
        }, {
            "$set": {
                "item_names": item_names
            }
        })
        logger.info(f"更新消息记录成功，修改条数 {res.modified_count}")
        return res.modified_count

    except Exception as e:
        logger.error(f"更新消息记录失败: {str(e)}")


if __name__ == "__main__":
    logger.info(get_messages_by_session_id(session_id="sess-ev5jxw8n67omr09auo3"))
    # update_message_item_names_by_id(["6a3a542fe3739bb50dd298a4"], ["666", "555"])
    # delete_messages_by_session_id("test")
    # add_message(
    #     session_id="6a3ccf008207c630ca70f890",
    #     text="RS PRO RS-12数字万用表规格什么样",
    #     role="user", item_names=["123", "456"])
