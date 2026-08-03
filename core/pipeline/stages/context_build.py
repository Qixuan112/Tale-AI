"""ContextBuildStage - 上下文构建

Order: 400
职责：整合元数据、图片识别、历史上下文、跨会话消息，构建最终 user_input
"""

import logging
from typing import Optional, Any, Dict
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext
from core.chat.context_builder import ContextBuilder
from core.config.provide import config_loader

logger = logging.getLogger(__name__)


class ContextBuildStage(PipelineStage):
    """上下文构建 Stage

    复用 core/chat/context_builder/ 模块，补充 #183 未接完的集成：
    1. 元数据段落（时间/消息/环境/富媒体）
    2. VLM 图片识别（带超时）
    3. 历史上下文（持久化模式走 SessionManager，否则走 context_buffer）
    4. 跨会话消息注入
    5. 组装最终 user_input
    """

    def __init__(
        self,
        context_builder: ContextBuilder,
        context_buffer: Optional[Dict] = None
    ):
        """初始化

        Args:
            context_builder: ContextBuilder 实例（已配置 MetadataBuilder/MediaRecognizer/HistoryProvider）
            context_buffer: 上下文缓冲区（BoundedCache，非持久化模式用）
        """
        super().__init__(order=400, name="context_build")
        self._context_builder = context_builder
        self._context_buffer = context_buffer

    async def process(self, ctx: PipelineContext) -> None:
        """构建上下文"""
        # 1. 调用 ContextBuilder 构建基础上下文（元数据 + VLM + 历史）
        persistence = config_loader.bot.bot.persistence_enabled
        window = config_loader.bot.context.chat_context_window

        base_input = await self._context_builder.build_input(
            processed=ctx.processed,
            platform_name=ctx.platform_name,
            context_buffer=self._context_buffer,
            window=window,
            persistence_enabled=persistence,
            session_enabled=ctx.session_enabled
        )

        # 2. 追加跨会话消息
        sections = [base_input]

        if ctx.inbox_msgs:
            inbox_lines = ["[来自其他会话的消息]"]
            for m in ctx.inbox_msgs:
                inbox_lines.append(
                    f"- 来自 {m['from_sid']}: {m['content']}"
                )
            sections.append("\n".join(inbox_lines))

        if ctx.accessible_sessions:
            sess_list = ", ".join(ctx.accessible_sessions)
            sections.append(f"[可通信会话] {sess_list}")

        # 3. 组装最终 user_input
        ctx.user_input = "\n\n".join(sections)

        logger.debug(
            "上下文构建完成: user_input=%d 字符",
            len(ctx.user_input)
        )
