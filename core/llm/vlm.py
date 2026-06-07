"""
VLM (Vision Language Model) Agent
==================================
多模态 LLM agent，用于图片识别。
每次调用发送文本+图片，返回文字描述。
"""

from typing import List, Optional

import httpx
from openai import OpenAI

from ..bus import bus
from ..utils import get_logger
from ..config.provide import config_loader

logger = get_logger(__name__)


class VlmLLM:
    """多模态视觉语言模型，单次无状态图片识别。"""

    MAX_IMAGES = 4

    def __init__(self, api_key=None, model=None, url=None):
        cfg = config_loader.vlm_api
        self.api_key = api_key or cfg.get("api_key", "")
        self.model = model or cfg.get("model", "")
        self.base_url = url or cfg.get("url", "")

        self._client = None
        if self.api_key and self.base_url:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )

        bus.on("config_reloaded", self._on_config_reloaded)

    def _on_config_reloaded(self):
        cfg = config_loader.vlm_api
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("url", "")
        model = cfg.get("model", "")
        if api_key:
            self.api_key = api_key
        if base_url:
            self.base_url = base_url
        if model:
            self.model = model
        if self.api_key and self.base_url:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        logger.info("VlmLLM: 配置已热更新")

    def _ensure_client(self) -> bool:
        if self._client is not None:
            return True
        if not self.api_key or not self.base_url:
            logger.warning("VlmLLM 未配置 API key 或 base_url，跳过调用")
            return False
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        return True

    def chat_with_image(self, text: str, image_paths: List[str]) -> Optional[str]:
        """发送文本+图片到多模态模型，返回文字描述。"""
        if not self._ensure_client():
            return None

        import base64
        from pathlib import Path

        content_parts = []
        if text.strip():
            content_parts.append({"type": "text", "text": text})

        for i, img_path in enumerate(image_paths[:self.MAX_IMAGES]):
            try:
                p = Path(img_path)
                if not p.is_absolute():
                    p = Path.cwd() / p
                if not p.exists():
                    logger.warning("图片不存在: %s", p)
                    continue
                with open(p, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                ext = p.suffix.lower().lstrip(".")
                mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                            "gif": "image/gif", "webp": "image/webp"}
                mime = mime_map.get(ext, "image/png")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{img_data}"}
                })
            except Exception as e:
                logger.warning("读取图片失败 %s: %s", img_path, e)

        if len(image_paths) > self.MAX_IMAGES:
            logger.warning("图片数量 %d 超过上限 %d", len(image_paths), self.MAX_IMAGES)

        if not content_parts:
            return None

        messages = [{"role": "user", "content": content_parts}]

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("VlmLLM API 调用失败: %s", e)
            return None


_vlm_instance: Optional[VlmLLM] = None


def get_vlm_llm() -> VlmLLM:
    global _vlm_instance
    if _vlm_instance is None:
        _vlm_instance = VlmLLM()
    return _vlm_instance
