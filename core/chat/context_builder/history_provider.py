"""HistoryProvider - 历史消息提供器

从会话管理器或上下文缓冲区加载历史消息。
"""

import logging
from typing import Optional, Any, Dict, List


logger = logging.getLogger(__name__)


class HistoryProvider:
    """历史消息提供器"""

    def __init__(self, session_manager: Optional[Any] = None):
        """初始化历史提供器

        Args:
            session_manager: 会话管理器实例
        """
        self._session_manager = session_manager

    async def get_history_context(
        self,
        processed,
        context_buffer: Optional[Dict] = None,
        window: int = 5,
        persistence_enabled: bool = False,
        session_enabled: bool = True
    ) -> str:
        """获取历史上下文

        Args:
            processed: ProcessedMessage 实例
            context_buffer: 上下文缓冲区（BoundedCache）
            window: 上下文窗口大小
            persistence_enabled: 是否启用持久化
            session_enabled: 当前会话是否启用

        Returns:
            格式化的历史上下文字符串，无历史时返回空字符串
        """
        # 持久化模式下，历史由 SessionManager 通过 set_session 加载
        # 不需要在这里拼接
        if persistence_enabled and self._session_manager and session_enabled:
            logger.debug("持久化模式：历史已通过 set_session 加载")
            return ""

        # 非持久化模式：从上下文缓冲区获取
        if not context_buffer:
            return ""

        key = processed.group_id or processed.sender_id
        if not key:
            return ""

        buffer = context_buffer.get(key)
        if not buffer:
            return ""

        # 排除缓冲区末条（即当前消息），避免重复
        recent = buffer[-(window + 1):-1] if len(buffer) > 1 else []
        if not recent:
            return ""

        lines = []
        for msg in recent:
            sender = msg.get('sender', 'Unknown')
            text = msg.get('text', '')
            file_names = ", ".join(
                f.get('name', '') for f in (msg.get('files') or [])[:3]
            )

            if text:
                line = f"[{sender}] {text}".rstrip()
                if file_names:
                    line += f" [文件: {file_names}]"
            elif file_names:
                line = f"[{sender}] [文件: {file_names}]"
            else:
                line = f"[{sender}] [图片]"

            lines.append(line)

        if lines:
            return "---\n以下是最近的聊天记录：\n" + "\n".join(lines) + "\n---"

        return ""
