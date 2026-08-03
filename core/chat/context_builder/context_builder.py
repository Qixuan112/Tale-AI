"""ContextBuilder - 上下文构建器

整合 MetadataBuilder、MediaRecognizer 和 HistoryProvider，
构建完整的用户输入上下文。
"""

import logging
from typing import Optional, Dict, Any
from core.adapter.message_processor import ProcessedMessage
from .metadata_builder import MetadataBuilder
from .media_recognizer import MediaRecognizer
from .history_provider import HistoryProvider


logger = logging.getLogger(__name__)


class ContextBuilder:
    """上下文构建器，整合元数据、图片识别和历史"""

    def __init__(
        self,
        metadata_builder: MetadataBuilder,
        media_recognizer: Optional[MediaRecognizer] = None,
        history_provider: Optional[HistoryProvider] = None
    ):
        """初始化上下文构建器

        Args:
            metadata_builder: 元数据构建器
            media_recognizer: 图片识别器（可选）
            history_provider: 历史提供器（可选）
        """
        self._metadata_builder = metadata_builder
        self._media_recognizer = media_recognizer
        self._history_provider = history_provider

    async def build_input(
        self,
        processed: ProcessedMessage,
        platform_name: str,
        context_buffer: Optional[Dict] = None,
        window: int = 5,
        persistence_enabled: bool = False,
        session_enabled: bool = True
    ) -> str:
        """构建完整的用户输入上下文

        Args:
            processed: 处理后的消息
            platform_name: 平台名称
            context_buffer: 上下文缓冲区
            window: 历史窗口大小
            persistence_enabled: 是否启用持久化
            session_enabled: 当前会话是否启用

        Returns:
            完整的用户输入字符串
        """
        # 1. 格式化用户消息
        user_text = self._metadata_builder.format_user_message(processed)

        # 2. 构建元数据
        metadata = self._metadata_builder.build_metadata(
            processed, platform_name, user_text
        )

        # 3. 图片识别（如果有图片且配置了识别器）
        image_recognition_text = ""
        if self._media_recognizer and processed.images:
            result = await self._media_recognizer.recognize_images(
                processed.images,
                prompt=processed.text or ""
            )
            if result:
                image_recognition_text = f"[图片识别结果]\n{result}"

        # 4. 历史上下文（修复问题#8：纯图消息也需要加载历史）
        context_text = ""
        if self._history_provider:
            # 不再检查 processed.text，纯图消息也应该有历史上下文
            context_text = await self._history_provider.get_history_context(
                processed,
                context_buffer=context_buffer,
                window=window,
                persistence_enabled=persistence_enabled,
                session_enabled=session_enabled
            )

        # 5. 组装最终输入
        final_sections = [metadata]

        if image_recognition_text:
            final_sections.append(image_recognition_text)

        if context_text:
            final_sections.append(context_text)

        # 当前消息作为重点
        final_sections.append(f"## 当前消息\n{user_text}")

        return "\n\n".join(final_sections)
