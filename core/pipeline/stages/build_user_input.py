"""BuildUserInputStage - 构建用户输入

Order: 100
职责：格式化用户消息（[At xxx] [Reply xxx] 内容），构建元数据段落
"""

import logging
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class BuildUserInputStage(PipelineStage):
    """构建用户输入 Stage

    从 ProcessedMessage 提取并格式化：
    1. user_text: [At xxx] [Reply xxx] 消息内容
    2. platform_name: 平台标识
    3. is_group/target_id: 会话类型和目标
    """

    def __init__(self):
        super().__init__(order=100, name="build_user_input")

    async def process(self, ctx: PipelineContext) -> None:
        """构建用户输入"""
        processed = ctx.processed

        # 1. 平台名称
        ctx.platform_name = (
            processed.platform.value
            if processed.platform
            else ctx.adapter_instance or "unknown"
        )

        # 2. 会话类型和目标
        ctx.is_group = processed.group_id is not None
        ctx.target_id = (
            processed.group_id if ctx.is_group else processed.sender_id
        )

        # 3. 格式化用户消息：[At xxx] [Reply xxx] 内容
        msg_parts = []

        # At 标签
        if processed.at_targets:
            for at_id in processed.at_targets:
                msg_parts.append(f"[At {at_id}]")

        # Reply 标签
        if processed.reply_to:
            if processed.reply_text:
                msg_parts.append(f"[回复: {processed.reply_text}]")
            else:
                msg_parts.append(f"[Reply {processed.reply_to}]")

        # 消息内容
        msg_parts.append(processed.text or "")

        ctx.user_text = " ".join(msg_parts)
        ctx.persist_content = ctx.user_text  # 纯净原文，用于落库

        logger.debug(
            "用户输入: %s (%s, %s)",
            ctx.user_text[:50],
            ctx.platform_name,
            "群聊" if ctx.is_group else "私聊"
        )
