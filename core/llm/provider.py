"""
Provider 抽象层
===============
BaseProvider -> OpenAICompatibleProvider -> ProviderManager

支持多供应商注册、运行时切换、故障回退和模型列表获取。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import httpx
from openai import OpenAI

from ..utils import get_logger

logger = get_logger(__name__)


class BaseProvider(ABC):
    """LLM 供应商抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def chat(
        self,
        messages: list,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> Optional[str]:
        ...

    def health_check(self) -> bool:
        return True

    def get_models(self) -> list:
        return []


class OpenAICompatibleProvider(BaseProvider):
    """兼容 OpenAI API 格式的 LLM 供应商。"""

    def __init__(
        self,
        name: str,
        api_key: str,
        base_url: str,
        default_model: str = "",
        timeout: int = 120,
    ):
        self._name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._timeout = timeout
        self._client: Optional[OpenAI] = None

    @property
    def name(self) -> str:
        return self._name

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
            )
        return self._client

    def chat(
        self,
        messages: list,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> Optional[str]:
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("[%s] API 调用失败: %s", self._name, e)
            return None

    def health_check(self) -> bool:
        try:
            self._get_client().models.list()
            return True
        except Exception:
            logger.warning("[%s] health check 失败", self._name, exc_info=True)
            return False

    def get_models(self) -> list:
        try:
            models = self._get_client().models.list()
            return sorted(m.id for m in models)
        except Exception:
            logger.warning("[%s] 获取模型列表失败", self._name, exc_info=True)
            return []


class ImageGenProvider(BaseProvider):
    """文生图供应商（OpenAI / SiliconFlow 兼容的 /images/generations 接口）。"""

    def __init__(
        self,
        name: str,
        api_key: str,
        base_url: str,
        default_model: str = "",
        timeout: int = 120,
    ):
        self._name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    def chat(self, messages, model, temperature=0.7, max_tokens=2048, **kwargs):
        logger.warning("[%s] ImageGenProvider 不支持 chat 调用", self._name)
        return None

    def generate_image(self, prompt: str, model: str, size: str = "1024x1024") -> Optional[str]:
        """文生图，返回图片 URL 或本地路径（provider 返回 base64 时落盘）。"""
        if not model:
            logger.warning("[%s] 未配置 image_gen 模型", self._name)
            return None
        url = f"{self.base_url}/images/generations"
        # 按 base_url 分流：三家字段互斥，混塞会 400
        low_url = self.base_url.lower()
        if "siliconflow" in low_url:
            payload = {"model": model, "prompt": prompt, "image_size": size, "batch_size": 1}
        elif "volces.com" in low_url:
            # 火山方舟 Seedream：size 用档位（2K/4K），不认 WxH；最少 ~3686400 像素
            payload = {
                "model": model, "prompt": prompt, "size": "2K",
                "response_format": "url", "watermark": True,
                "stream": False, "sequential_image_generation": "disabled",
            }
        else:
            payload = {"model": model, "prompt": prompt, "size": size, "n": 1}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with httpx.Client(timeout=httpx.Timeout(self._timeout, connect=10.0)) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error("[%s] 图片生成 API 调用失败: %s", self._name, e)
            return None

        # 兼容 OpenAI ({data:[{url}]}) 与 SiliconFlow ({images:[{url}]}) 两种响应
        items = data.get("data") or data.get("images") or []
        if not items:
            logger.warning("[%s] 图片生成响应无 data/images 字段: %s", self._name, data)
            return None
        first = items[0]
        if first.get("url"):
            return first["url"]
        # base64 落盘（走 TempFileManager 带自动清理）
        b64 = first.get("b64_json")
        if b64:
            return self._save_b64(b64)
        logger.warning("[%s] 图片生成响应项无 url/b64_json: %s", self._name, first)
        return None

    @staticmethod
    def _save_b64(b64: str) -> Optional[str]:
        """base64 图片落盘到 temp 目录（带自动清理），返回路径。"""
        import base64
        import time
        from ..utils.temp_manager import temp_manager
        try:
            img_bytes = base64.b64decode(b64)
            filename = f"imggen_{int(time.time() * 1000)}.png"
            return temp_manager.save_image(img_bytes, filename)
        except Exception as e:
            logger.warning("base64 图片落盘失败: %s", e)
            return None


class ProviderManager:
    """多供应商 LLM 管理器（单例）。

    职责：
    - 从 config_loader 自动注册供应商
    - 解析 routing.yaml 确定模型类型对应的供应商和模型
    - 提供 chat_with_fallback 自动故障回退
    - 健康检查与模型列表获取
    - 监听 config_reloaded 事件自动刷新
    """

    _instance: Optional["ProviderManager"] = None
    _subscribed = False

    def __new__(cls) -> "ProviderManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._providers: Dict[str, BaseProvider] = {}
        self._initialized = True
        self._reload_from_config()
        if not ProviderManager._subscribed:
            from ..bus import bus

            bus.on("config_reloaded", self._on_config_reloaded)
            ProviderManager._subscribed = True

    def _reload_from_config(self) -> None:
        from ..config.provide import config_loader

        providers_config = config_loader.providers
        if not providers_config:
            logger.info("ProviderManager: 无供应商配置")
            self._providers = {}
            return

        new_providers: Dict[str, BaseProvider] = {}
        for name, cfg in providers_config.items():
            fmt = (getattr(cfg, "format", "") or "").lower()
            tp = (getattr(cfg, "type", "") or "").lower()
            # type 优先于 format：format: openai + type: image_gen 应注册为 ImageGenProvider
            if tp == "image_gen":
                provider = ImageGenProvider(
                    name=name,
                    api_key=getattr(cfg, "api_key", ""),
                    base_url=getattr(cfg, "base_url", ""),
                    default_model=getattr(cfg, "model", ""),
                    timeout=getattr(cfg, "timeout", 120) or 120,
                )
                new_providers[name] = provider
                logger.debug("ProviderManager: 注册图片生成供应商 '%s' (%s)", name, provider.base_url)
            elif fmt == "openai" or tp == "llm":
                provider = OpenAICompatibleProvider(
                    name=name,
                    api_key=getattr(cfg, "api_key", ""),
                    base_url=getattr(cfg, "base_url", ""),
                    default_model=getattr(cfg, "model", ""),
                    timeout=getattr(cfg, "timeout", 120) or 120,
                )
                new_providers[name] = provider
                logger.debug("ProviderManager: 注册供应商 '%s' (%s)", name, provider.base_url)

        self._providers = new_providers
        logger.info("ProviderManager: 已注册 %d 个供应商", len(new_providers))

    def _on_config_reloaded(self) -> None:
        logger.info("ProviderManager: 配置重载，重新注册供应商")
        self._reload_from_config()

    # ============ 注册/查询 ============

    def register(self, name: str, provider: BaseProvider) -> None:
        """手动注册一个供应商。"""
        self._providers[name] = provider
        logger.info("ProviderManager: 已注册供应商 '%s'", name)

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        return self._providers.get(name)

    @property
    def providers(self) -> Dict[str, BaseProvider]:
        return dict(self._providers)

    @property
    def default_provider(self) -> Optional[BaseProvider]:
        for p in self._providers.values():
            return p
        return None

    # ============ 路由解析 ============

    def resolve(self, model_type: str) -> Tuple[Optional[BaseProvider], str]:
        """解析模型类型对应的 (provider, model)。

        查找优先级：
        1. routing.yaml 指定 provider -> 查找对应 provider
        2. routing.yaml 指定 model -> 使用该 model
        3. provider 自身的 default_model
        4. 无配置 -> (None, "")
        """
        from ..config.provide import config_loader

        model_mapping = getattr(config_loader.models, model_type, None)

        provider_name = getattr(model_mapping, "provider", "") if model_mapping else ""
        model_name = getattr(model_mapping, "model", "") if model_mapping else ""

        provider: Optional[BaseProvider] = None
        if provider_name:
            provider = self._providers.get(provider_name)

        if provider is None:
            provider = self.default_provider

        if not model_name and provider:
            model_name = provider.default_model if isinstance(provider, OpenAICompatibleProvider) else ""

        return provider, model_name

    def get_for_fallback(self, model_type: str) -> List[Tuple[BaseProvider, str]]:
        """获取 (provider, model) 候选列表，主选+备选。"""
        primary_provider, primary_model = self.resolve(model_type)
        candidates: List[Tuple[BaseProvider, str]] = []
        seen: set = set()

        if primary_provider:
            candidates.append((primary_provider, primary_model))
            seen.add(id(primary_provider))

        for provider in self._providers.values():
            if id(provider) not in seen:
                model = provider.default_model if isinstance(provider, OpenAICompatibleProvider) else ""
                candidates.append((provider, model))
                seen.add(id(provider))

        return candidates

    # ============ 便捷方法 ============

    def get_api_config(self, model_type: str) -> Dict[str, str]:
        """获取 API 配置字典（向后兼容 ConfigLoader.get_api_config）。"""
        provider, model = self.resolve(model_type)
        if provider is None or not isinstance(provider, OpenAICompatibleProvider):
            return {"api_key": "", "model": "", "url": ""}
        return {
            "api_key": provider.api_key,
            "model": model or provider.default_model,
            "url": provider.base_url,
        }

    def chat_with_fallback(
        self,
        model_type: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """发送消息，主供应商失败自动回退到备选。"""
        candidates = self.get_for_fallback(model_type)
        for provider, model in candidates:
            if not model:
                continue
            result = provider.chat(messages, model, temperature, max_tokens)
            if result is not None:
                return result
        logger.error("[ProviderManager] 所有供应商均失败")
        return None

    def health_check_all(self) -> Dict[str, bool]:
        """对所有注册供应商执行健康检查。"""
        return {name: p.health_check() for name, p in self._providers.items()}


# 全局单例
provider_manager = ProviderManager()
