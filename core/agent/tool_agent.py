"""
ToolAgent - Stateless tool-calling agent

Simplified version of ToolLLM for function calling.
"""

import asyncio
from typing import Dict, List, Optional
from ..utils import get_logger
from .base import LLMAgent

logger = get_logger(__name__)


class ToolAgent(LLMAgent):
    """Stateless tool-calling agent using OpenAI function calling format"""

    def __init__(self, provider, tools: Optional[List[Dict]] = None):
        """Initialize ToolAgent

        Args:
            provider: LLM provider with async chat() method
            tools: List of tool definitions (OpenAI format)
        """
        self._provider = provider
        self._tools = tools or []
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._lock_manager_mutex = asyncio.Lock()

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create per-session lock"""
        async with self._lock_manager_mutex:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    async def generate(
        self,
        messages: List[Dict],
        session_id: str,
        timeout: Optional[float] = 60.0
    ) -> str:
        """Generate tool call with concurrency control

        Args:
            messages: Conversation history
            session_id: Session identifier
            timeout: Timeout in seconds (default 60s)

        Returns:
            Tool call response (JSON string)

        Raises:
            asyncio.TimeoutError: If LLM call exceeds timeout
        """
        session_lock = await self._get_session_lock(session_id)
        async with session_lock:
            try:
                chat_method = self._provider.chat
                if asyncio.iscoroutinefunction(chat_method):
                    reply = await asyncio.wait_for(
                        chat_method(messages, tools=self._tools),
                        timeout=timeout
                    )
                else:
                    loop = asyncio.get_event_loop()
                    reply = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: chat_method(messages, tools=self._tools)),
                        timeout=timeout
                    )
                return reply
            except asyncio.TimeoutError:
                logger.error(f"ToolAgent timeout for session {session_id} after {timeout}s")
                raise

    def get_config(self) -> dict:
        """Get agent configuration"""
        return {
            "tools_count": len(self._tools),
            "active_sessions": len(self._session_locks)
        }
