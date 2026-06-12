"""
检索管道
Embed query → FAISS search → 格式化结果
"""

from typing import List, Optional
from .embedder import BaseEmbedder
from .vector_store import FaissVectorStore


class Retriever:
    """端到端检索器"""

    def __init__(self, embedder: BaseEmbedder, store: FaissVectorStore,
                 top_k: int = 5, threshold: float = 0.0,
                 max_context_length: int = 2000):
        self._embedder = embedder
        self._store = store
        self._top_k = top_k
        self._threshold = threshold
        self._max_context_length = max_context_length

    def retrieve(self, query: str) -> List[str]:
        """检索并返回格式化后的文本片段列表"""
        query_vec = self._embedder.embed([query])
        results = self._store.search(query_vec, top_k=self._top_k)
        filtered = [(chunk, score) for chunk, score in results if score >= self._threshold]

        context_parts = []
        total_len = 0
        for chunk, score in filtered:
            text = chunk.get("text", "")
            source = chunk.get("metadata", {}).get("source", chunk.get("kb_name", "unknown"))
            entry = f"[来自: {source}]\n{text}"
            if total_len + len(entry) > self._max_context_length:
                remaining = self._max_context_length - total_len
                if remaining > 50:
                    context_parts.append(entry[:remaining])
                break
            context_parts.append(entry)
            total_len += len(entry)

        return context_parts

    def format_for_prompt(self, query: str) -> str:
        """检索并为 prompt 注入格式化"""
        results = self.retrieve(query)
        if not results:
            return ""
        parts = [
            "\n## 知识库参考信息",
            "以下内容来自知识库，请参考这些信息回答用户问题：\n",
        ]
        parts.extend(results)
        return "\n\n".join(parts)
