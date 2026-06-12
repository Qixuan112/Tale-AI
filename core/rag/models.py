"""
RAG 知识库系统数据模型
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class KnowledgeBaseConfig:
    """单个知识库的配置"""
    name: str = "default"
    enabled: bool = True
    embedder: str = "openai"
    embed_model: str = "text-embedding-3-small"
    top_k: int = 3
    similarity_threshold: float = 0.0
    description: str = ""


@dataclass
class RAGConfig:
    """顶层 RAG 知识库配置"""
    enabled: bool = False
    default_embedder: str = "openai"
    openai_embedding_api_key: str = ""
    openai_embedding_base_url: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    bge_model_name: str = "BAAI/bge-small-zh-v1.5"
    bge_device: str = "cpu"
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    inject_into_chat: bool = True
    inject_order: int = 5
    max_context_length: int = 2000
    knowledge_bases: List[KnowledgeBaseConfig] = field(default_factory=list)


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
