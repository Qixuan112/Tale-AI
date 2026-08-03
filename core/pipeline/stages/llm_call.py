"""LLMCallStage - LLM 调用

Order: 500
职责：调用 ChatLLM 或 ChatAgent 生成回复，支持快照管理和超时处理
"""

import asyncio
import logging
import functools
from typing import Optional, Dict, List, Any
from concurrent.futures import ThreadPoolExecutor

from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class LLMCallStage(PipelineStage):
    """LLM 调用 Stage

    支持两种模式：
    1. ChatAgent 模式（无状态）：调用 generate(messages, session_id, timeout)
    2. ChatLLM 模式（有状态）：调用 chat(user_input, persist_content, save_to_session)

    依赖注入：
    - chat_agent: Optional[ChatAgent] - 无状态 Agent（优先使用）
    - chat_llm: Optional[ChatLLM] - 有状态 LLM（兼容模式）
    - session_manager: Optional[SessionManager] - 会话管理器
    - llm_executor: ThreadPoolExecutor - LLM 调用专用线程池
    - chat_snapshots: Dict[str, List[Dict]] - 快照缓存
    """

    def __init__(
        self,
        chat_llm: Optional[Any] = None,
        chat_agent: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        llm_executor: Optional[ThreadPoolExecutor] = None,
        chat_snapshots: Optional[Dict[str, List[Dict]]] = None,
    ):
        super().__init__(order=500, name="llm_call")
        self.chat_llm = chat_llm
        self.chat_agent = chat_agent
        self.session_manager = session_manager
        self.llm_executor = llm_executor
        self.chat_snapshots = chat_snapshots or {}

    async def process(self, ctx: PipelineContext) -> None:
        """调用 LLM 生成回复"""
        if not ctx.user_input:
            logger.warning("user_input 为空，跳过 LLM 调用")
            ctx.chatllm_reply = ""
            return

        if self.chat_llm is None and self.chat_agent is None:
            logger.error("ChatLLM 和 ChatAgent 均未初始化")
            ctx.chatllm_reply = "[系统错误] LLM 未初始化，请检查 services.yaml 配置"
            return

        # 获取会话 ID
        sid = ctx.sid or ""

        try:
            if self.chat_agent is not None:
                # ── ChatAgent 无状态路径 ──
                reply = await self._call_chat_agent(ctx, sid)
            else:
                # ── ChatLLM 有状态路径 ──
                reply = await self._call_chat_llm(ctx, sid)

            ctx.chatllm_reply = reply or ""

        except asyncio.TimeoutError:
            logger.error("LLM 调用超时 [sid=%s]", sid)
            raise
        except Exception as e:
            logger.error("LLM 调用失败 [sid=%s]: %s", sid, e)
            raise

    async def _call_chat_agent(self, ctx: PipelineContext, sid: str) -> str:
        """调用 ChatAgent.generate()（无状态模式）

        从 SessionManager 加载历史 + 快照，追加当前用户消息，调用 generate()。
        结果写入快照缓存（延迟持久化）。

        Args:
            ctx: 管道上下文
            sid: 会话 ID

        Returns:
            AI 回复文本
        """
        # 1. 组装消息列表：历史 + 快照 + 当前用户消息
        messages = self._get_session_messages(sid)
        messages.append({"role": "user", "content": ctx.user_input})

        # 2. 调用 ChatAgent.generate()
        reply = await self.chat_agent.generate(
            messages=messages,
            session_id=sid,
            timeout=60.0,
        )

        if reply is None:
            logger.error("ChatAgent 返回空响应")
            reply = ""

        # 3. 更新快照缓存（本轮追加段，延迟落库）
        if (reply or ctx.persist_content) and sid:
            snap = self.chat_snapshots.setdefault(sid, [])

            # 追加用户原文（persist_content 非空时）
            if ctx.persist_content:
                snap.append({
                    "role": "user",
                    "content": ctx.persist_content or ctx.user_input
                })

            # 追加或更新 assistant 回复
            if reply:
                if snap and snap[-1].get("role") == "assistant":
                    # 工具轮次：更新上一条 assistant 回复
                    snap[-1] = {"role": "assistant", "content": reply}
                else:
                    # 新回复：追加
                    snap.append({"role": "assistant", "content": reply})

            # 限制快照长度，防内存泄漏
            if len(snap) > 40:
                self.chat_snapshots[sid] = snap[-20:]

        return reply

    async def _call_chat_llm(self, ctx: PipelineContext, sid: str) -> str:
        """调用 ChatLLM.chat()（有状态模式）

        在线程池中执行同步 API 调用，避免阻塞事件循环。

        Args:
            ctx: 管道上下文
            sid: 会话 ID

        Returns:
            AI 回复文本
        """
        if self.llm_executor is None:
            # 无线程池时，直接同步调用（测试场景）
            logger.warning("llm_executor 未注入，使用同步调用")
            return self.chat_llm.chat(
                ctx.user_input,
                ctx.persist_content,
                save_to_session=False,
            )

        # 在专用线程池中执行同步 API 调用
        # 使用 functools.partial 包装，以便传递关键字参数
        loop = asyncio.get_running_loop()
        chat_func = functools.partial(
            self.chat_llm.chat,
            ctx.user_input,
            ctx.persist_content,
            save_to_session=False,
        )
        reply = await loop.run_in_executor(self.llm_executor, chat_func)

        return reply

    def _get_session_messages(self, sid: str) -> List[Dict]:
        """组装 ChatAgent 模式的会话消息列表

        将会话历史（SessionManager）与快照（本轮追加段）合并。
        - system 头由 ChatLLMAdapter 显式注入（不在此处理）
        - 持久化模式：历史来自 SessionManager.get_memory(sid)
        - 快照缓存本轮未落库的追加消息

        Args:
            sid: 会话 ID

        Returns:
            消息列表（[{role, content}, ...]）
        """
        messages: List[Dict] = []

        # 1. 加载持久化历史
        if self.session_manager is not None:
            try:
                # 禁用的会话不加载历史
                session = self.session_manager.get_session(sid)
                if session is None or session.enabled:
                    messages.extend(self.session_manager.get_memory(sid))
            except Exception as e:
                logger.debug("读取会话历史失败: %s", e)

        # 2. 追加快照（本轮未落库的追加段）
        messages.extend(self.chat_snapshots.get(sid, []))

        return messages
