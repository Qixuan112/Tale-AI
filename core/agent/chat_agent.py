"""
ChatAgent - Stateless chat agent with per-session concurrency control

Fixes issue #1: Removes global lock, enables concurrent processing
Fixes issue #6: Adds timeout protection to all LLM calls
"""

import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
from ..utils import get_logger
from .base import LLMAgent

logger = get_logger(__name__)

# 同步 provider 的专用线程池：超时的 LLM 调用无法真正取消正在执行的
# 阻塞函数（线程只能泄漏到调用自然结束），专用小池把这类"僵尸线程"
# 隔离在 ChatAgent 内部，避免耗尽事件循环的默认 executor 线程
# （重复超时会让默认池的线程全部被慢调用占据）。线程池模块级共享，
# 所有 ChatAgent 实例复用（会话锁/信号量仍按实例隔离）。
_SYNC_EXECUTOR = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="chat-agent-sync"
)


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

    def __init__(self, provider, max_concurrency: int = 3, max_sessions: int = 1000):
        """Initialize ChatAgent

        Args:
            provider: LLM provider with async chat() method
            max_concurrency: Max concurrent LLM calls (default 3)
            max_sessions: Max per-session locks kept in memory (default 1000).
                Beyond this, LRU eviction removes the least-recently-used
                session lock, but never one that is currently held or has
                waiters (eviction is deferred until the lock is free).
        """
        self._provider = provider
        self._session_locks: "OrderedDict[str, asyncio.Lock]" = OrderedDict()
        self._max_sessions = max_sessions
        self._global_semaphore = asyncio.Semaphore(max_concurrency)
        self._lock_manager_mutex = asyncio.Lock()
        self._max_concurrency = max_concurrency

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create per-session lock (LRU-bounded, see __init__)

        Eviction safety: a lock is only evicted while it is not held and has
        no waiters. If the oldest lock is still in use, eviction is deferred
        (the lock is skipped) so a lock that is being acquired or awaited by
        another coroutine is never removed out from under it. Evicting a
        free lock is safe: any future acquire for that session simply creates
        a fresh lock, and per-session serialization only requires that the
        *currently active* holder uses a single shared instance.

        Args:
            session_id: Session identifier

        Returns:
            Lock for this session
        """
        async with self._lock_manager_mutex:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[session_id] = lock
            else:
                self._session_locks.move_to_end(session_id)
            while len(self._session_locks) > self._max_sessions:
                oldest_id = next(iter(self._session_locks))
                oldest_lock = self._session_locks[oldest_id]
                if oldest_lock.locked():
                    # 锁被持有/等待中：跳过（不淘汰），下个新会话插入时再尝试
                    break
                del self._session_locks[oldest_id]
            return lock

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
                        # Sync provider - run in dedicated executor. Note:
                        # wait_for() cancels the awaiting coroutine but cannot
                        # cancel the blocking call once it is running inside
                        # the executor thread; the thread runs until the call
                        # finishes on its own. The dedicated pool (4 workers)
                        # confines such lingering threads to ChatAgent instead
                        # of exhausting the default executor.
                        loop = asyncio.get_event_loop()
                        reply = await asyncio.wait_for(
                            loop.run_in_executor(_SYNC_EXECUTOR, chat_method, messages),
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
            "max_sessions": self._max_sessions,
            "active_sessions": len(self._session_locks),
        }
