"""
知识库管理器
统一管理知识库的文档上传、索引、检索、重建等全生命周期
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..utils import get_logger

logger = get_logger(__name__)

# RAG 注入上下文时使用的标记头，用于在 ChatLLM 中精准定位已注入的消息
RAG_KNOWLEDGE_HEADER = "## 知识库参考信息"


class KnowledgeManager:
    """知识库管理器（单例）"""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self._config = None  # RAGConfig
        self._embedder = None
        self._stores = {}       # kb_name -> FaissVectorStore
        self._retrievers = {}   # kb_name -> Retriever
        self._documents = {}    # kb_name -> List[DocumentRecord]
        self._data_dir = None
        self._rag_data_dir = None
        self._document_index_path = None
        self._lock = threading.Lock()

    def initialize(self, config, data_dir: str):
        """
        初始化知识库管理器

        Args:
            config: RAGConfig 实例
            data_dir: data/ 目录路径
        """
        self._config = config
        self._data_dir = Path(data_dir)
        self._rag_data_dir = self._data_dir / "rag"
        self._rag_data_dir.mkdir(parents=True, exist_ok=True)
        self._document_index_path = self._rag_data_dir / "document_index.json"

        with self._lock:
            # 显式释放旧 FAISS 索引（native 内存，不受 GC 管理）
            for store in self._stores.values():
                try:
                    store.close()
                except Exception as e:
                    logger.debug("关闭 FAISS 索引时出错: %s", e)
            self._stores.clear()
            self._retrievers.clear()

            if not config.enabled:
                self._embedder = None
                return

            from .embedder import create_embedder
            try:
                self._embedder = create_embedder(config)
            except Exception as e:
                logger.warning("知识库 Embedder 初始化失败 (非致命): %s", e)
                self._embedder = None
                return

            from .vector_store import FaissVectorStore
            from .retriever import Retriever

            for kb in config.knowledge_bases:
                if not kb.enabled:
                    continue
                try:
                    store = FaissVectorStore(
                        str(self._rag_data_dir / "index"),
                        kb.name,
                        dimension=self._embedder.dimension,
                    )
                    self._stores[kb.name] = store
                    self._retrievers[kb.name] = Retriever(
                        embedder=self._embedder,
                        store=store,
                        top_k=kb.top_k,
                        threshold=kb.similarity_threshold,
                        max_context_length=config.max_context_length,
                    )
                except Exception as e:
                    logger.warning("知识库 '%s' 初始化失败 (非致命): %s", kb.name, e)

        self._load_document_index()
        logger.info("知识库系统初始化完成, 已加载 %d 个知识库, %d 个文档",
                     len(self._stores),
                     sum(len(docs) for docs in self._documents.values()))

    # ---- 文档管理 ----

    def upload_document(self, kb_name: str, file_path: str, filename: str):
        """
        上传并索引文档

        Args:
            kb_name: 目标知识库名称
            file_path: 文件实际路径
            filename: 原始文件名
        Returns:
            DocumentRecord
        """
        from .document_parser import DocumentParser
        from .chunker import TextChunker

        parser = DocumentParser()
        raw_text = parser.parse(file_path)

        chunker = TextChunker(
            chunk_size=self._config.chunk_size,
            overlap=self._config.chunk_overlap,
        )
        chunks = chunker.chunk(raw_text)

        doc_id = str(uuid.uuid4())
        store = self._stores.get(kb_name)
        if store is None:
            raise ValueError(f"知识库 '{kb_name}' 未找到或已禁用")

        # 构建分块记录
        chunk_records = []
        for i, text in enumerate(chunks):
            chunk_records.append({
                "chunk_id": f"{doc_id}_{i}",
                "doc_id": doc_id,
                "kb_name": kb_name,
                "text": text,
                "metadata": {"source": filename, "chunk_index": i},
            })

        # 向量化并添加索引
        if not self._embedder:
            raise RuntimeError("Embedder 未初始化，请检查 API 密钥或 BGE 模型配置")
        chunk_texts = [c["text"] for c in chunk_records]
        embeddings = self._embedder.embed(chunk_texts)
        store.add(embeddings, chunk_records)

        from .models import DocumentRecord
        record = DocumentRecord(
            id=doc_id,
            kb_name=kb_name,
            filename=filename,
            file_type=Path(filename).suffix.lower().lstrip("."),
            file_size=Path(file_path).stat().st_size,
            chunk_count=len(chunks),
            uploaded_at=datetime.now(timezone.utc).isoformat(),
            status="indexed",
        )

        with self._lock:
            if kb_name not in self._documents:
                self._documents[kb_name] = []
            self._documents[kb_name].append(record)
            self._save_document_index()

        logger.info("文档已索引: %s (%d 分块) → 知识库 '%s'", filename, len(chunks), kb_name)
        return record

    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        with self._lock:
            for kb_name, records in list(self._documents.items()):
                for rec in list(records):
                    if rec.id == doc_id:
                        records.remove(rec)
                        self.rebuild_index(kb_name)
                        self._save_document_index()
                        logger.info("文档已删除: %s (从知识库 '%s')", rec.filename, kb_name)
                        return True
        return False

    def rebuild_index(self, kb_name: str):
        """重建知识库索引"""
        from .document_parser import DocumentParser
        from .chunker import TextChunker

        store = self._stores.get(kb_name)
        if store is None:
            return
        store.clear()

        records = self._documents.get(kb_name, [])
        if not records:
            return

        parser = DocumentParser()
        chunker = TextChunker(
            chunk_size=self._config.chunk_size,
            overlap=self._config.chunk_overlap,
        )

        all_chunk_records = []
        for rec in records:
            doc_path = self._rag_data_dir / "documents" / kb_name / rec.id / rec.filename
            if not doc_path.exists():
                continue
            try:
                raw_text = parser.parse(str(doc_path))
                chunks = chunker.chunk(raw_text)
                for i, text in enumerate(chunks):
                    all_chunk_records.append({
                        "chunk_id": f"{rec.id}_{i}",
                        "doc_id": rec.id,
                        "kb_name": kb_name,
                        "text": text,
                        "metadata": {"source": rec.filename, "chunk_index": i},
                    })
            except Exception as e:
                logger.warning("重建索引时解析文档 '%s' 失败: %s", rec.filename, e)

        if all_chunk_records:
            if not self._embedder:
                logger.error("重建索引失败：Embedder 未初始化")
                return
            texts = [c["text"] for c in all_chunk_records]
            embeddings = self._embedder.embed(texts)
            store.rebuild_from_chunks(embeddings, all_chunk_records)

        logger.info("知识库 '%s' 索引已重建 (%d 分块)", kb_name, len(all_chunk_records))

    # ---- 检索 ----

    def retrieve(self, query: str) -> str:
        """
        检索知识库并格式化为 prompt 注入文本

        Args:
            query: 用户输入
        Returns:
            格式化后的知识库参考文本，无结果时返回空字符串
        """
        if not self._config or not self._config.enabled or not self._embedder:
            return ""

        all_parts = []
        for kb_name, retriever in self._retrievers.items():
            try:
                parts = retriever.retrieve(query)
                all_parts.extend(parts)
            except Exception as e:
                logger.debug("知识库 '%s' 检索失败: %s", kb_name, e)

        if not all_parts:
            return ""

        lines = [
            "\n" + RAG_KNOWLEDGE_HEADER,
            "以下内容来自知识库，请参考这些信息回答用户的问题：",
            "",
        ]
        lines.extend(all_parts)
        return "\n\n".join(lines)

    # ---- 持久化 ----

    def _save_document_index(self):
        if self._document_index_path is None:
            return
        data = {}
        for kb_name, records in self._documents.items():
            data[kb_name] = [
                {
                    "id": r.id, "kb_name": r.kb_name, "filename": r.filename,
                    "file_type": r.file_type, "file_size": r.file_size,
                    "chunk_count": r.chunk_count, "uploaded_at": r.uploaded_at,
                    "status": r.status, "error_message": r.error_message,
                }
                for r in records
            ]
        with open(self._document_index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_document_index(self):
        with self._lock:
            self._documents = {}
            if self._document_index_path and self._document_index_path.exists():
                try:
                    with open(self._document_index_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    from .models import DocumentRecord
                    for kb_name, records in data.items():
                        self._documents[kb_name] = [
                            DocumentRecord(**r) for r in records
                        ]
                except Exception as e:
                    logger.warning("加载文档索引失败: %s", e)

    # ---- 状态查询 ----

    def get_status(self) -> dict:
        if not self._config:
            return {"enabled": False}
        return {
            "enabled": self._config.enabled,
            "knowledge_bases": {
                name: {
                    "chunks": store.size,
                    "documents": len(self._documents.get(name, [])),
                }
                for name, store in self._stores.items()
            } if self._stores else {},
        }

    def get_documents(self, kb_name: str) -> list:
        return self._documents.get(kb_name, [])


# 全局单例
knowledge_manager = KnowledgeManager()
