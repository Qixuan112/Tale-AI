"""
RAG 工具函数
"""
import os
from pathlib import Path


def ensure_dir(path: str) -> str:
    """确保目录存在，返回路径"""
    Path(path).mkdir(parents=True, exist_ok=True)
    return path
