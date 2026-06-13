"""
RAG 知识库系统数据模型

KnowledgeBaseConfig 和 RAGConfig 的规范定义在 core/config/model.py，
此处仅导入并额外定义 RAG 内部数据模型。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from ..config.model import KnowledgeBaseConfig, RAGConfig  # noqa: F401


@dataclass
class DocumentRecord:
    """文档元数据"""
    id: str = ""
    kb_name: str = ""
    filename: str = ""
    file_type: str = ""
    file_size: int = 0
    chunk_count: int = 0
    uploaded_at: str = ""
    status: str = "pending"  # pending | indexed | error
    error_message: str = ""


@dataclass
class ChunkRecord:
    """文档分块记录"""
    chunk_id: str = ""
    doc_id: str = ""
    kb_name: str = ""
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
