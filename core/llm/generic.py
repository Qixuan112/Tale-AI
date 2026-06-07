"""
通用 LLM Agent
==============
不绑定固定角色/系统提示词的通用 LLM 类。
可用于 XML 修复、插件调用、文本处理等任意场景。

使用方式:
    from core.llm.generic import get_generic_llm

    generic = get_generic_llm()
    result = generic.chat(system_prompt="你是翻译助手", user_message="hello")
"""

from typing import Optional

import httpx
from openai import OpenAI

from ..bus import bus
from ..config import MAX_CONTEXT
from ..config.provide import config_loader
from ..utils import get_logger

logger = get_logger(__name__)


class GenericLLM:
    """通用 LLM，不绑定固定角色/系统提示词。
    每次调用由使用方传入 system prompt，灵活适配多种场景。
    """

    def __init__(self, api_key=None, model=None, url=None):
        cfg = config_loader.generic_api
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
        """配置重载后热更新 API 客户端。"""
        cfg = config_loader.generic_api
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
        logger.info("GenericLLM: 配置已热更新")

    def _ensure_client(self) -> bool:
        """确保客户端可用，返回 False 表示不可用。"""
        if self._client is not None:
            return True
        if not self.api_key or not self.base_url:
            logger.warning("GenericLLM 未配置 API key 或 base_url，跳过调用")
            return False
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        return True

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """
        单次无状态调用。

        Args:
            system_prompt: 本次调用的系统提示词（由使用方定义角色/任务）
            user_message: 用户输入
            temperature: 温度参数，默认 0（适合修复/格式化等确定性任务）
            max_tokens: 最大输出 token

        Returns:
            LLM 回复文本，失败返回 None
        """
        if not self._ensure_client():
            return None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("GenericLLM API 调用失败: %s", e)
            return None

    def chat_with_messages(
        self,
        messages: list,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """
        多轮对话接口，供需要上下文的插件使用。

        Args:
            messages: 完整消息列表，格式 [{"role": "system|user|assistant", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大输出 token

        Returns:
            LLM 回复文本，失败返回 None
        """
        if not self._ensure_client():
            return None

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("GenericLLM API 调用失败: %s", e)
            return None


# 模块级单例
_generic_llm_instance: Optional[GenericLLM] = None


def get_generic_llm() -> GenericLLM:
    """获取 GenericLLM 懒加载单例。"""
    global _generic_llm_instance
    if _generic_llm_instance is None:
        _generic_llm_instance = GenericLLM()
    return _generic_llm_instance
