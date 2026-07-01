from core.logger import logger

if __name__ == "__main__":
    # 测试
    a = {'27e32778-d91c-43d6-a782-baff5fb502ae': {'running_list': ['answer_question'],
                                                  'done_list': ['query_hyde_result_by_embedding',
                                                                'confirm_item_name_by_user_query',
                                                                'order_result_by_rerank',
                                                                'order_embedding_result_by_rrf',
                                                                'query_result_by_embedding', 'query_result_by_mcp'],
                                                  'status': 'processing', 'result': {}}}

    running_list = a['27e32778-d91c-43d6-a782-baff5fb502ae'].get('running_list', [])
    logger.info(running_list)

    target = list(filter(lambda a: a != 'answer_question', running_list))
    a["27e32778-d91c-43d6-a782-baff5fb502ae"]["running_list"] = target
    logger.info(target)
    logger.info(a["27e32778-d91c-43d6-a782-baff5fb502ae"])
