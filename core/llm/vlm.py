"""
VLM (Vision Language Model) Agent
==================================
多模态 LLM agent，用于图片识别。
每次调用发送文本+图片，返回文字描述。
"""

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import List, Optional

from ..bus import bus
from ..utils import get_logger
from .provider import OpenAICompatibleProvider, provider_manager

logger = get_logger(__name__)

# 默认识别 prompt：调用方未提供 text 时使用
_RECOGNIZE_PROMPT = "请详细描述这张图片的内容（包括文字、物体、场景、人物、颜色等），用简洁的中文。"

_CACHE_PATH = Path("data/cache/image_desc.json")
# 串行化缓存 read-modify-write，避免并发丢更新/读到半截 JSON
_cache_lock = threading.Lock()


def _load_desc_cache() -> dict:
    try:
        if _CACHE_PATH.exists():
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("读取图片描述缓存失败: %s", e)
    return {}


def _save_desc_cache(cache: dict) -> None:
    """原子写：先写临时文件再 os.replace，避免并发读到半截 JSON。"""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _CACHE_PATH)
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
        """发送文本+图片到多模态模型，返回文字描述。

        支持针对性提问（text 作为识别问题）与多图联合推理（所有图同一条 message）。
        缓存键 = MD5(所有图字节拼接 + 识别prompt)，同一组图+同一问题不重复调用。
        """
        if not self._ensure_provider():
            return None

        import base64

        recognize_prompt = (text.strip() if text and text.strip() else _RECOGNIZE_PROMPT)
        paths = image_paths[:self.MAX_IMAGES]
        if len(image_paths) > self.MAX_IMAGES:
            logger.warning("图片数量 %d 超过上限 %d", len(image_paths), self.MAX_IMAGES)

        # 读取所有图字节，构造多模态 content
        content_parts = [{"type": "text", "text": recognize_prompt}]
        hash_parts = [recognize_prompt.encode("utf-8")]
        for img_path in paths:
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
            ext = p.suffix.lower().lstrip(".")
            mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                        "gif": "image/gif", "webp": "image/webp"}
            mime = mime_map.get(ext, "image/png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            })
            hash_parts.append(img_bytes)

        # 只有 text part、无图 → 无法识别
        if len(content_parts) <= 1:
            return None

        cache_key = hashlib.md5(b"\x00".join(hash_parts)).hexdigest()

        # 两阶段：锁内查缓存命中；锁外调慢 API；锁内回写。避免持锁调 VLM 串行化所有 miss。
        with _cache_lock:
            if cache_key in _load_desc_cache():
                logger.debug("VLM 缓存命中: %s", cache_key)
                return _load_desc_cache()[cache_key]

        messages = [{"role": "user", "content": content_parts}]
        try:
            desc = self._provider.chat(messages=messages, model=self.model, max_tokens=1024)
        except Exception as e:
            logger.error("VlmLLM API 调用失败: %s", e)
            return None

        if desc:
            with _cache_lock:
                cache = _load_desc_cache()
                cache[cache_key] = desc
                _save_desc_cache(cache)
            return desc
        return None


_vlm_instance: Optional[VlmLLM] = None


def get_vlm_llm() -> VlmLLM:
    global _vlm_instance
    if _vlm_instance is None:
        _vlm_instance = VlmLLM()
    return _vlm_instance
