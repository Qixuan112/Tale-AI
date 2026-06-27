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

    KNOWN_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

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
        # 优先使用显式配置的维度，否则用已知模型映射表，最后通过探针请求获取
        self._dim = dimensions or self.KNOWN_DIMENSIONS.get(model)

    @property
    def dimension(self) -> int:
        if self._dim is None:
            # 模型不在已知映射表中，用一条短文本探针获取维度
            probe = self._client.embeddings.create(input=["a"], model=self._model)
            self._dim = len(probe.data[0].embedding)
        return self._dim

    def _supports_dimensions(self) -> bool:
        """仅 text-embedding-3 系列支持显式指定 dimensions；
        ada-002 及第三方兼容端点会因该参数返回 400，故不发送"""
        return self._model.startswith("text-embedding-3")

    def _build_kwargs(self, input_batch: list) -> dict:
        """构造传给 embeddings.create 的参数"""
        kwargs: dict = {"input": input_batch, "model": self._model}
        # 仅在模型支持时才发送 dimensions，避免 ada-002/兼容端点报错
        if self._dim is not None and self._supports_dimensions():
            kwargs["dimensions"] = self._dim
        return kwargs

    def _l2_normalize(self, arr: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.array([], dtype=np.float32)
        # 分批发送避免超长请求
        batch_size = 20
        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self._client.embeddings.create(**self._build_kwargs(batch))
            all_vectors.extend(r.embedding for r in resp.data)
        arr = np.array(all_vectors, dtype=np.float32)
        # 首次调用时从响应推断维度
        if self._dim is None and arr.shape[0] > 0:
            self._dim = arr.shape[1]
        # 归一化使内积等价于余弦相似度（与 IndexFlatIP + BGEEmbedder 行为一致）
        return self._l2_normalize(arr)


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
    # 路由优先：如果 routing.yaml 中配置了 embeddding，优先使用
    try:
        from ..config.loader import config_loader
        routing_emb = config_loader.models.embedding
        if routing_emb and routing_emb.provider and routing_emb.model:
            provider = config_loader.providers.get(routing_emb.provider)
            if provider and provider.api_key:
                return OpenAIEmbedder(
                    api_key=provider.api_key,
                    base_url=provider.base_url,
                    model=routing_emb.model,
                )
    except Exception:
        pass  # fall through to legacy path

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
