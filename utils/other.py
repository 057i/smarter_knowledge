import sys


def get_current_func_name():
    """
    返回当前运行函数
    :return:
    """
    return sys._getframe().f_code.co_name