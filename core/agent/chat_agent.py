"""
ChatAgent - Stateless chat agent with per-session concurrency control

Fixes issue #1: Removes global lock, enables concurrent processing
Fixes issue #6: Adds timeout protection to all LLM calls
"""

import asyncio
from typing import Dict, List, Optional
from ..utils import get_logger
from .base import LLMAgent

logger = get_logger(__name__)


class ChatAgent(LLMAgent):
    """Stateless chat agent with per-session locks and global semaphore

    Design:
    - Per-session lock: Same user's messages processed serially (order preserved)
    - Global semaphore: Limits max concurrent LLM calls (default 3)
    - Different sessions can run concurrently

    Performance:
    - 3 users concurrent: ~1s (vs ~3s with global lock)
    - Same user serial: ~3s (order preserved)
    - 5 users with limit: ~2s (semaphore working)
    """

    def __init__(self, provider, max_concurrency: int = 3):
        """Initialize ChatAgent

        Args:
            provider: LLM provider with async chat() method
            max_concurrency: Max concurrent LLM calls (default 3)
        """
        self._provider = provider
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._global_semaphore = asyncio.Semaphore(max_concurrency)
        self._lock_manager_mutex = asyncio.Lock()
        self._max_concurrency = max_concurrency

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create per-session lock

        Args:
            session_id: Session identifier

        Returns:
            Lock for this session
        """
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
        """Generate LLM response with concurrency control

        Args:
            messages: Conversation history
            session_id: Session identifier
            timeout: Timeout in seconds (default 60s)

        Returns:
            LLM response string

        Raises:
            asyncio.TimeoutError: If LLM call exceeds timeout
        """
        # 1. Global concurrency control (max 3 concurrent calls)
        async with self._global_semaphore:
            # 2. Per-session lock (same user's messages serial)
            session_lock = await self._get_session_lock(session_id)
            async with session_lock:
                # 3. Call LLM with timeout protection (fixes issue #6)
                try:
                    # Check if provider.chat is async or sync
                    chat_method = self._provider.chat
                    if asyncio.iscoroutinefunction(chat_method):
                        # Async provider
                        reply = await asyncio.wait_for(
                            chat_method(messages),
                            timeout=timeout
                        )
                    else:
                        # Sync provider - run in executor
                        loop = asyncio.get_event_loop()
                        reply = await asyncio.wait_for(
                            loop.run_in_executor(None, chat_method, messages),
                            timeout=timeout
                        )
                    return reply
                except asyncio.TimeoutError:
                    logger.error(f"LLM call timeout for session {session_id} after {timeout}s")
                    raise

    def get_config(self) -> dict:
        """Get agent configuration

        Returns:
            Configuration dictionary
        """
        return {
            "max_concurrency": self._max_concurrency,
            "active_sessions": len(self._session_locks)
        }
