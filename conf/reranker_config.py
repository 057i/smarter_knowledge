# 导入核心依赖：数据类、环境变量读取、路径处理
from dataclasses import dataclass
import os
from dotenv import load_dotenv

# 提前加载.env配置文件（保持和原代码一致，只需执行一次）
load_dotenv()


@dataclass
class RerankerConfig:
    bge_reranker_name: str  # 本地模型名
    bge_reranker_path: str
    bge_reranker_device: str  # 模型仓库标识
    bge_reranker_fp16: bool  # 是否开启半精度加速（1=True/0=False）


reranker_config = RerankerConfig(
    bge_reranker_name=os.getenv("BGE_RERANKER_NAME"),
    bge_reranker_path=os.getenv("BGE_RERANKER_PATH"),
    bge_reranker_device=os.getenv("BGE_RERANKER_DEVICE"),
    # 特殊处理：将.env中的1/0转为布尔值，兼容常见的数字/字符串格式
    bge_reranker_fp16=os.getenv("BGE_RERANKER_FP16") in ("1", "True", "true", 1)
)
