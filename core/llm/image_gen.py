"""
ImageGenerator — 文生图 Agent
==================================
单例，按 routing.yaml 的 image_gen 路由解析 provider/model，
调用 ImageGenProvider.generate_image 返回图片 URL 或本地路径。
"""

from typing import Optional

from ..bus import bus
from ..utils import get_logger
from .provider import ImageGenProvider, provider_manager

logger = get_logger(__name__)


class ImageGenerator:
    """文生图生成器，单次无状态。"""

    def __init__(self):
        self._on_config_reloaded()
        bus.on("config_reloaded", self._on_config_reloaded)

    def _on_config_reloaded(self):
        provider, model = provider_manager.resolve("image_gen")
        self._provider = provider if isinstance(provider, ImageGenProvider) else None
        self._model = model or (provider.default_model if isinstance(provider, ImageGenProvider) else "")
        if self._provider is None:
            logger.debug("ImageGenerator: 未配置 image_gen provider")

    def _ensure(self) -> bool:
        if self._provider is not None and self._model:
            return True
        self._on_config_reloaded()
        return self._provider is not None and bool(self._model)

    def generate(self, prompt: str, size: str = "1024x1024") -> Optional[str]:
        """文生图，返回图片 URL 或本地路径；不可用时返回 None。"""
        if not prompt.strip():
            return None
        if not self._ensure():
            logger.warning("ImageGenerator 未配置，跳过图片生成")
            return None
        try:
            url = self._provider.generate_image(prompt, self._model, size)
            if url:
                logger.info("图片生成成功: %s", url[:120])
            return url
        except Exception as e:
            logger.error("图片生成失败: %s", e, exc_info=True)
            return None


_image_gen_instance: Optional[ImageGenerator] = None


def get_image_generator() -> ImageGenerator:
    global _image_gen_instance
    if _image_gen_instance is None:
        _image_gen_instance = ImageGenerator()
    return _image_gen_instance
