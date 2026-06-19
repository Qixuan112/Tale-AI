"""
VLM (Vision Language Model) Agent
==================================
多模态 LLM agent，用于图片识别。
每次调用发送文本+图片，返回文字描述。
"""

import hashlib
import json
from pathlib import Path
from typing import List, Optional

from ..bus import bus
from ..utils import get_logger
from .provider import OpenAICompatibleProvider, provider_manager

logger = get_logger(__name__)

# 固定识别 prompt：保证同一张图的描述稳定，可缓存
_RECOGNIZE_PROMPT = "请详细描述这张图片的内容（包括文字、物体、场景、人物、颜色等），用简洁的中文。"

_CACHE_PATH = Path("data/cache/image_desc.json")


def _load_desc_cache() -> dict:
    try:
        if _CACHE_PATH.exists():
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("读取图片描述缓存失败: %s", e)
    return {}


def _save_desc_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("写入图片描述缓存失败: %s", e)


class VlmLLM:
    """多模态视觉语言模型，单次无状态图片识别。"""

    MAX_IMAGES = 4

    def __init__(self, api_key=None, model=None, url=None):
        cfg = provider_manager.get_api_config("vlm")
        self.api_key = api_key or cfg.get("api_key", "")
        self.model = model or cfg.get("model", "")
        self.base_url = url or cfg.get("url", "")

        self._provider: Optional[OpenAICompatibleProvider] = None
        self._init_provider()

        bus.on("config_reloaded", self._on_config_reloaded)

    def _init_provider(self):
        if self.api_key and self.base_url:
            self._provider = OpenAICompatibleProvider(
                name="vlm",
                api_key=self.api_key,
                base_url=self.base_url,
                default_model=self.model,
            )
        else:
            self._provider = None

    def _on_config_reloaded(self):
        cfg = provider_manager.get_api_config("vlm")
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("url", "")
        model = cfg.get("model", "")
        if api_key:
            self.api_key = api_key
        if base_url:
            self.base_url = base_url
        if model:
            self.model = model
        self._init_provider()
        logger.info("VlmLLM: 配置已热更新")

    def _ensure_provider(self) -> bool:
        if self._provider is not None:
            return True
        if not self.api_key or not self.base_url:
            logger.warning("VlmLLM 未配置 API key 或 base_url，跳过调用")
            return False
        self._init_provider()
        return self._provider is not None

    def chat_with_image(self, text: str, image_paths: List[str]) -> Optional[str]:
        """对每张图调用 VLM 识别，返回拼接后的描述。

        按图片字节 MD5 缓存描述（data/cache/image_desc.json），同一张图不重复调用。
        统一使用固定识别 prompt，忽略传入的 text（用户文本已在 ChatLLM 上下文里）。
        """
        if not self._ensure_provider():
            return None

        import base64

        cache = _load_desc_cache()
        cache_dirty = False
        descs = []

        for img_path in image_paths[:self.MAX_IMAGES]:
            try:
                p = Path(img_path)
                if not p.is_absolute():
                    p = Path.cwd() / p
                if not p.exists():
                    logger.warning("图片不存在: %s", p)
                    continue
                img_bytes = p.read_bytes()
            except Exception as e:
                logger.warning("读取图片失败 %s: %s", img_path, e)
                continue

            md5 = hashlib.md5(img_bytes).hexdigest()
            if md5 in cache:
                logger.debug("VLM 缓存命中: %s", md5)
                descs.append(cache[md5])
                continue

            ext = p.suffix.lower().lstrip(".")
            mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                        "gif": "image/gif", "webp": "image/webp"}
            mime = mime_map.get(ext, "image/png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts = [
                {"type": "text", "text": _RECOGNIZE_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]
            messages = [{"role": "user", "content": content_parts}]
            try:
                desc = self._provider.chat(messages=messages, model=self.model, max_tokens=1024)
            except Exception as e:
                logger.error("VlmLLM API 调用失败: %s", e)
                continue
            if desc:
                cache[md5] = desc
                cache_dirty = True
                descs.append(desc)

        if len(image_paths) > self.MAX_IMAGES:
            logger.warning("图片数量 %d 超过上限 %d", len(image_paths), self.MAX_IMAGES)

        if cache_dirty:
            _save_desc_cache(cache)

        if not descs:
            return None
        return "\n".join(f"[图{i+1}] {d}" for i, d in enumerate(descs))


_vlm_instance: Optional[VlmLLM] = None


def get_vlm_llm() -> VlmLLM:
    global _vlm_instance
    if _vlm_instance is None:
        _vlm_instance = VlmLLM()
    return _vlm_instance
