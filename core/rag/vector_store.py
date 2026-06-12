"""
FAISS 向量存储
每个知识库一个独立的 FAISS 索引 + 分块映射 JSON
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple


class FaissVectorStore:
    """轻量 FAISS 向量存储，支持持久化"""

    def __init__(self, index_dir: str, kb_name: str, dimension: int = 512):
        self._index_dir = Path(index_dir) / kb_name
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._kb_name = kb_name
        self._dimension = dimension

        self._index_path = self._index_dir / "index.faiss"
        self._mapping_path = self._index_dir / "mapping.json"

        self._index = None
        self._chunks: List[dict] = []
        self._load()

    def _load(self):
        import faiss
        if self._index_path.exists() and self._mapping_path.exists():
            self._index = faiss.read_index(str(self._index_path))
            with open(self._mapping_path, "r", encoding="utf-8") as f:
                self._chunks = json.load(f)
        else:
            self._index = faiss.IndexFlatIP(self._dimension)
            self._chunks = []

    def _save(self):
        import faiss
        if self._index is not None and self._index.ntotal > 0:
            faiss.write_index(self._index, str(self._index_path))
        with open(self._mapping_path, "w", encoding="utf-8") as f:
            json.dump(self._chunks, f, ensure_ascii=False, indent=2)

    def add(self, embeddings: np.ndarray, chunk_records: List[dict]):
        """
        添加向量和对应的分块记录

        Args:
            embeddings: (N, D) float32 数组
            chunk_records: 分块元数据列表，每项包含 chunk_id, doc_id, text, metadata
        """
        self._index.add(embeddings)
        self._chunks.extend(chunk_records)
        self._save()

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> List[Tuple[dict, float]]:
        """搜索相似分块，返回 [(chunk_dict, score), ...]"""
        if self._index.ntotal == 0:
            return []
        distances, indices = self._index.search(query_vec.reshape(1, -1), min(top_k, self._index.ntotal))
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            results.append((self._chunks[idx], float(dist)))
        return results

    def clear(self):
        """清空索引"""
        import faiss
        self._index = faiss.IndexFlatIP(self._dimension)
        self._chunks = []
        if self._index_path.exists():
            self._index_path.unlink()
        if self._mapping_path.exists():
            self._mapping_path.unlink()

    @property
    def size(self) -> int:
        return self._index.ntotal if self._index else 0

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def get_document_chunks(self, doc_id: str) -> List[dict]:
        return [c for c in self._chunks if c.get("doc_id") == doc_id]

    def remove_document(self, doc_id: str):
        """移除指定文档的所有分块，触发索引重建"""
        remaining = [c for c in self._chunks if c.get("doc_id") != doc_id]
        if len(remaining) == len(self._chunks):
            return
        # 重建索引（需要调用者提供 embedding，或外部重新索引）
        self._chunks = remaining
        # 标记需要重建，调用方负责 rebuild
        self._index = None
        self._save_mapping_only()

    def _save_mapping_only(self):
        if self._mapping_path:
            with open(self._mapping_path, "w", encoding="utf-8") as f:
                json.dump(self._chunks, f, ensure_ascii=False, indent=2)

    def rebuild_from_chunks(self, embeddings: np.ndarray):
        """从已有的分块列表重建 FAISS 索引"""
        import faiss
        self._index = faiss.IndexFlatIP(self._dimension)
        if embeddings.shape[0] > 0:
            self._index.add(embeddings)
        self._save()
