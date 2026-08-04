"""HistorySaveStage - 历史记录持久化

Order: 900
Always run: True（即使管道提前终止也必须执行）

职责：
1. 持久化最终回复（SessionManager 或 ChatLLM）
2. Ack 跨会话消息（防止重复投递）
3. 通知文件发送失败（注入到上下文缓冲区或会话记忆）
"""

import logging
import time
from typing import Optional, Any, Dict
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext
from core.config.provide import config_loader

logger = logging.getLogger(__name__)


class HistorySaveStage(PipelineStage):
    """历史记录持久化 Stage

    根据 core/main.py 的 _persist_and_ack() 逻辑实现：
    - ChatAgent 路径：通过 _persist_snapshot 将快照落库到 SessionManager
    - ChatLLM 路径：调用 ChatLLM._save_session_memory() 持久化
    - 跨会话消息 ack：调用 bridge.ack() 确认已处理的消息

    always_run=True 确保即使管道提前终止（skip_reply/parse_error），
    也能正确持久化记忆和 ack 消息，防止重复投递。
    """

    def __init__(
        self,
        chat_llm: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        bridge: Optional[Any] = None,
        chat_agent: Optional[Any] = None,
        chat_snapshots: Optional[Dict] = None,
        chat_context_buffer: Optional[Dict] = None
    ):
        """初始化

        Args:
            chat_llm: ChatLLM 实例（有状态模式）
            session_manager: SessionManager 实例（无状态模式持久化）
            bridge: BridgeState 实例（跨会话消息 ack）
            chat_agent: ChatAgent 实例（用于判断是否 ChatAgent 路径）
            chat_snapshots: 会话快照字典（ChatAgent 模式）
            chat_context_buffer: 上下文缓冲区字典（用于文件失败通知）
        """
        super().__init__(order=900, name="history_save", always_run=True)
        self._chat_llm = chat_llm
        self._session_manager = session_manager
        self._bridge = bridge
        self._chat_agent = chat_agent
        self._chat_snapshots = chat_snapshots if chat_snapshots is not None else {}
        self._chat_context_buffer = chat_context_buffer if chat_context_buffer is not None else {}

    async def process(self, ctx: PipelineContext) -> None:
        """持久化历史记录并 ack 跨会话消息

        逻辑参考 core/main.py 的 _persist_and_ack():
        1. ChatAgent 路径 → _persist_snapshot
        2. ChatLLM 路径 → _save_session_memory
        3. 跨会话消息 → bridge.ack
        4. 文件发送失败通知 → 注入上下文
        """
        # 1. 持久化最终回复
        await self._persist_history(ctx)

        # 2. Ack 跨会话消息（防止重复投递）
        await self._ack_inbox_messages(ctx)

        # 3. 文件发送失败通知
        if ctx.failed_files:
            await self._notify_file_upload_failure(ctx)

        logger.debug(
            "历史记录已持久化: sid=%s, persist_content=%s",
            ctx.sid,
            bool(ctx.persist_content)
        )

    async def _persist_history(self, ctx: PipelineContext) -> None:
        """持久化对话历史

        根据模式选择持久化方式：
        - ChatAgent 模式：通过 _persist_snapshot 落库快照
        - ChatLLM 模式：调用 _save_session_memory
        """
        try:
            # ChatAgent 路径：无状态，从快照落库
            if self._chat_agent is not None and ctx.sid:
                self._persist_snapshot(ctx.sid)
            # ChatLLM 路径：有状态，直接保存当前会话
            elif self._chat_llm is not None and ctx.persist_content:
                # 只有当 ChatLLM.current_sid 存在时才保存
                if hasattr(self._chat_llm, 'current_sid') and self._chat_llm.current_sid:
                    self._chat_llm._save_session_memory(ctx.persist_content)
        except Exception as e:
            # 持久化失败不应该阻止流程，只记录错误
            logger.error("持久化历史记录失败: %s", e, exc_info=True)

    def _persist_snapshot(self, sid: str) -> None:
        """将 ChatAgent 模式的会话快照落库到 SessionManager

        参考 core/main.py 的 _persist_snapshot() 实现：
        - 从 chat_snapshots 读取快照
        - 成对写入 user+assistant 消息
        - 落库成功后清空快照
        - 无持久化模式下直接清空快照
        """
        if not sid:
            return

        # 无持久化模式：直接清空快照
        if self._session_manager is None:
            self._chat_snapshots.pop(sid, None)
            return

        try:
            # 检查会话是否启用
            session = self._session_manager.get_session(sid)
            if session is not None and not session.enabled:
                return  # 禁用的会话不持久化新记忆

            # 获取快照
            snap = self._chat_snapshots.get(sid, [])

            # 成对写入 user+assistant 消息
            i = 0
            while i < len(snap) - 1:
                if snap[i].get("role") == "user" and snap[i + 1].get("role") == "assistant":
                    self._session_manager.append_memory(
                        sid,
                        {"role": "user", "content": snap[i].get("content", "")},
                        {"role": "assistant", "content": snap[i + 1].get("content", "")},
                    )
                    i += 2
                else:
                    i += 1

            # 清空快照
            self._chat_snapshots.pop(sid, None)
        except Exception as e:
            logger.debug("会话快照落库失败: %s", e)

    async def _ack_inbox_messages(self, ctx: PipelineContext) -> None:
        """确认跨会话消息已处理（防止重复投递）

        从 inbox_msgs 提取 id 列表，调用 bridge.ack() 确认。
        只 ack 有 'id' 字段的消息。
        """
        if not ctx.inbox_msgs or not ctx.sid or not self._bridge:
            return

        try:
            # 提取消息 ID（过滤掉没有 id 的消息）
            message_ids = [m["id"] for m in ctx.inbox_msgs if m.get("id")]

            if message_ids:
                await self._bridge.ack(ctx.sid, message_ids)
                logger.debug(
                    "跨会话消息已确认: sid=%s, count=%d",
                    ctx.sid,
                    len(message_ids)
                )
        except Exception as e:
            # Ack 失败记录错误但不抛出（不阻止流程）
            logger.error("确认跨会话消息失败: %s", e, exc_info=True)

    async def _notify_file_upload_failure(self, ctx: PipelineContext) -> None:
        """将文件发送失败信息注入 AI 上下文

        参考 core/main.py _notify_file_upload_failure (1296-1330行)
        根据持久化模式选择注入方式：
        - 非持久化模式：写入 context_buffer（插入到当前消息之前）
        - 持久化模式：写入 SessionManager 会话记忆
        """
        if not ctx.failed_files:
            return

        try:
            file_list = "、".join(ctx.failed_files[:5])
            notice = f"[系统通知] 文件发送失败：{file_list}"

            # 判断是否使用持久化模式
            persistence = config_loader.bot.bot.persistence_enabled
            # 与 _store_to_context_buffer 相同的判定：持久化模式下 buffer 无人读取
            # （use_ctx 恒为 False）且不经过截断，写入只会造成内存无限增长
            use_buffer = not (persistence and self._session_manager)

            # 写入上下文缓冲区（插入到当前消息之前，避免被 [:-1] 跳过）
            key = ctx.processed.group_id or ctx.processed.sender_id
            if key and use_buffer:
                entries = self._chat_context_buffer.setdefault(key, [])
                entry = {
                    "sender": "系统",
                    "text": notice,
                    "time": time.strftime("%H:%M"),
                    "images": [],
                    "files": [],
                }
                entries.insert(max(len(entries) - 1, 0), entry)

            # 持久化路径：写入会话记忆，供下次 set_session 时 AI 感知
            if persistence and self._session_manager and ctx.sid:
                # append_memory 需要 user+assistant 均非空，用占位保证配对完整性
                self._session_manager.append_memory(
                    ctx.sid,
                    {"role": "user", "content": notice},
                    {"role": "assistant", "content": "（文件上传失败通知已被记录）"},
                )

            logger.info("已注入文件发送失败通知: %s", notice)

        except Exception as e:
            # 通知注入失败不应阻止流程
            logger.error("注入文件失败通知失败: %s", e, exc_info=True)
