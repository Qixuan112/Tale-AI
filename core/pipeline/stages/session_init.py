"""SessionInitStage - 会话初始化

Order: 300
职责：构造 sid，调用 set_session，处理跨会话消息 inbox
"""

import logging
from typing import Optional, Any
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext
from core.config.provide import config_loader

logger = logging.getLogger(__name__)


class SessionInitStage(PipelineStage):
    """会话初始化 Stage

    1. 构造 sid（platform:type:target_id）
    2. 获取会话状态（session_enabled）
    3. 调用 ChatLLM.set_session() 加载历史（锁外执行，在 ContextBuildStage 之前）
    4. 消费跨会话 inbox 消息
    """

    def __init__(
        self,
        session_manager: Optional[Any] = None,
        chat_llm: Optional[Any] = None,
        bridge: Optional[Any] = None
    ):
        """初始化

        Args:
            session_manager: SessionManager 实例
            chat_llm: ChatLLM 实例（用于 set_session）
            bridge: BridgeState 实例（跨会话消息）
        """
        super().__init__(order=300, name="session_init")
        self._session_manager = session_manager
        self._chat_llm = chat_llm
        self._bridge = bridge

    async def process(self, ctx: PipelineContext) -> None:
        """初始化会话"""
        persistence = config_loader.bot.bot.persistence_enabled

        # 1. 构造 sid
        stype = "gm" if ctx.is_group else "dm"
        sid = f"{ctx.processed.platform.value}:{stype}:{ctx.target_id}"
        ctx.sid = sid

        # 2. 获取会话状态
        if persistence and self._session_manager:
            session_obj = self._session_manager.get_or_create(sid)
            ctx.session_enabled = session_obj.enabled
        else:
            # 即使未启用持久化，也需生成 sid 用于 per-session 锁隔离
            ctx.session_enabled = True

        # 3. set_session（有状态 ChatLLM 路径，ChatAgent 路径不需要）
        if self._chat_llm and sid:
            self._chat_llm.set_session(sid, load_history=ctx.session_enabled)

        # 4. 消费跨会话 inbox
        if sid and self._bridge:
            ctx.inbox_msgs = await self._bridge.consume(sid)
            if ctx.inbox_msgs:
                logger.info(
                    "跨会话消息: %d 条来自其他会话",
                    len(ctx.inbox_msgs)
                )

            # 获取可通信会话列表
            accessible = self._bridge.list_accessible(sid)
            if accessible:
                ctx.accessible_sessions = accessible

        logger.debug(
            "会话初始化: sid=%s, enabled=%s, inbox=%d",
            sid,
            ctx.session_enabled,
            len(ctx.inbox_msgs)
        )
