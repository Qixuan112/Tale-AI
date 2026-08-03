"""
PlanAgent - Stateless planning agent

Simplified version of PlanLLM for daily planning.
"""

import asyncio
from typing import Dict, List, Optional
from ..utils import get_logger
from .base import LLMAgent

logger = get_logger(__name__)


class PlanAgent(LLMAgent):
    """Stateless planning agent for daily schedule generation"""

    def __init__(self, provider):
        """Initialize PlanAgent

        Args:
            provider: LLM provider with async chat() method
        """
        self._provider = provider
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
        """Generate plan with concurrency control

        Args:
            messages: Planning prompt and context
            session_id: Session identifier
            timeout: Timeout in seconds (default 60s)

        Returns:
            Generated plan (JSON string)

        Raises:
            asyncio.TimeoutError: If LLM call exceeds timeout
        """
        session_lock = await self._get_session_lock(session_id)
        async with session_lock:
            try:
                chat_method = self._provider.chat
                if asyncio.iscoroutinefunction(chat_method):
                    reply = await asyncio.wait_for(
                        chat_method(messages),
                        timeout=timeout
                    )
                else:
                    loop = asyncio.get_event_loop()
                    reply = await asyncio.wait_for(
                        loop.run_in_executor(None, chat_method, messages),
                        timeout=timeout
                    )
                return reply
            except asyncio.TimeoutError:
                logger.error(f"PlanAgent timeout for session {session_id} after {timeout}s")
                raise

    def get_config(self) -> dict:
        """Get agent configuration"""
        return {
            "active_sessions": len(self._session_locks)
        }
