"""
Embedding 抽象层
支持 OpenAI Compatible API 和本地 BGE 模型
"""

from abc import ABC, abstractmethod
from typing import List, Optional

import numpy as np


class BaseEmbedder(ABC):
    """Embedding 模型抽象基类"""

    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        """将文本列表转换为向量，返回 (N, D) float32 数组"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """返回向量维度"""


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI Compatible Embedding API"""

    def __init__(self, api_key: str, base_url: str = "",
                 model: str = "text-embedding-3-small",
                 dimensions: Optional[int] = None):
        if not api_key:
            raise ValueError(
                "OpenAI Embedding API key 未配置，请在 knowledge.yaml 中设置 openai_embedding_api_key "
                "或使用本地 BGE 模型 (default_embedder: bge)"
            )
        import openai
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        # 优先使用显式配置的维度，否则首次 embed 时从结果推断
        self._dim = dimensions

    @property
    def dimension(self) -> int:
        if self._dim is None:
            raise RuntimeError("维度尚未初始化，请先调用 embed()")
        return self._dim

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.array([], dtype=np.float32)
        # 分批发送避免超长请求
        batch_size = 20
        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self._client.embeddings.create(input=batch, model=self._model)
            all_vectors.extend(r.embedding for r in resp.data)
        arr = np.array(all_vectors, dtype=np.float32)
        # 首次调用时从响应推断维度
        if self._dim is None and arr.shape[0] > 0:
            self._dim = arr.shape[1]
        return arr


class BGEEmbedder(BaseEmbedder):
    """本地 BGE 模型 (sentence-transformers)"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5",
                 device: str = "cpu"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers 未安装，请执行: pip install sentence-transformers"
            )
        self._model = SentenceTransformer(model_name, device=device)
        self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.array([], dtype=np.float32)
        return self._model.encode(
            texts, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)


def create_embedder(config) -> BaseEmbedder:
    """根据配置创建 Embedder"""
    if config.default_embedder == "openai" and config.openai_embedding_api_key:
        return OpenAIEmbedder(
            api_key=config.openai_embedding_api_key,
            base_url=config.openai_embedding_base_url,
            model=config.openai_embedding_model,
        )
    if config.default_embedder == "openai":
        # 回退：尝试从 services.yaml 中取第一个可用的 API 密钥
        from ..config.loader import config_loader
        provider = config_loader.get_active_provider("main_llm")
        if not provider or not provider.api_key:
            raise ValueError(
                "OpenAI Embedding 需要 API key：请在 knowledge.yaml 中设置 openai_embedding_api_key，"
                "或在 services.yaml 中配置 LLM 服务商"
            )
        return OpenAIEmbedder(api_key=provider.api_key, base_url=provider.base_url,
                              model=config.openai_embedding_model)
    return BGEEmbedder(model_name=config.bge_model_name,
                       device=config.bge_device)
