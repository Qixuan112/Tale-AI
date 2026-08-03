"""
Unit tests for ChatAgent lock management

Tests internal lock management mechanisms.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from core.agent import ChatAgent


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider"""
    provider = AsyncMock()

    async def mock_chat(messages, model=None, timeout=None):
        await asyncio.sleep(0.1)
        return "Response"

    provider.chat = mock_chat
    return provider


class TestChatAgentLockManagement:
    """Test ChatAgent internal lock management"""

    @pytest.mark.asyncio
    async def test_session_locks_created_on_demand(self, mock_llm_provider):
        """
        Session locks should be created lazily when first accessed

        Avoid memory overhead for inactive sessions
        """
        agent = ChatAgent(mock_llm_provider)
        assert len(agent._session_locks) == 0

        await agent.generate(
            messages=[{"role": "user", "content": "A"}],
            session_id="user1"
        )
        assert "user1" in agent._session_locks

        await agent.generate(
            messages=[{"role": "user", "content": "B"}],
            session_id="user2"
        )
        assert "user2" in agent._session_locks
        assert len(agent._session_locks) == 2

    @pytest.mark.asyncio
    async def test_session_locks_are_reentrant(self, mock_llm_provider):
        """
        Session locks must NOT be reentrant (use asyncio.Lock, not RLock)

        Reentrancy could mask bugs where agent calls itself recursively
        """
        agent = ChatAgent(mock_llm_provider)
        await agent.generate(
            messages=[{"role": "user", "content": "A"}],
            session_id="user1"
        )

        # Must be a plain asyncio.Lock (asyncio has no RLock; a reentrant
        # implementation would allow the same task to acquire twice)
        lock = agent._session_locks["user1"]
        assert isinstance(lock, asyncio.Lock)

        # Behavioral check: asyncio.Lock is NOT reentrant. Hold the lock,
        # then a second acquire from the same task must block and time out.
        await lock.acquire()
        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(lock.acquire(), timeout=0.2)
        finally:
            lock.release()

    @pytest.mark.asyncio
    async def test_lock_manager_is_thread_safe(self, mock_llm_provider):
        """
        Lock dictionary access must be thread-safe

        Multiple coroutines creating locks concurrently should not race
        """
        agent = ChatAgent(mock_llm_provider)

        # 100 coroutines requesting the same session lock at once
        locks = await asyncio.gather(*[
            agent._get_session_lock("user1")
            for _ in range(100)
        ])

        # All requests must return the SAME lock instance
        assert all(l is locks[0] for l in locks)
        assert len(agent._session_locks) == 1

    @pytest.mark.asyncio
    async def test_semaphore_configuration(self, mock_llm_provider):
        """
        Semaphore should be configurable via constructor

        Default: max_concurrent=3
        """
        agent = ChatAgent(mock_llm_provider, max_concurrency=5)
        assert agent._max_concurrency == 5
        assert agent._global_semaphore._value == 5

        # Default is 3 when not specified
        default_agent = ChatAgent(mock_llm_provider)
        assert default_agent._max_concurrency == 3

    @pytest.mark.asyncio
    async def test_lock_not_leaked_on_exception(self, mock_llm_provider):
        """
        CRITICAL: Lock must be released even if exception occurs

        Use try/finally or async context manager to ensure cleanup
        """
        agent = ChatAgent(mock_llm_provider)

        # Configure provider to raise exception
        original_chat = mock_llm_provider.chat

        async def failing_chat(messages, model=None, timeout=None):
            raise RuntimeError("LLM failed")

        mock_llm_provider.chat = failing_chat

        with pytest.raises(RuntimeError):
            await agent.generate(
                messages=[{"role": "user", "content": "X"}],
                session_id="user1"
            )

        # Lock should be released, next call should work
        mock_llm_provider.chat = original_chat
        result = await agent.generate(
            messages=[{"role": "user", "content": "Y"}],
            session_id="user1"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_semaphore_not_leaked_on_exception(self, mock_llm_provider):
        """
        CRITICAL: Semaphore permit must be released on exception

        Otherwise max_concurrent slots leak and system gets slower
        """
        agent = ChatAgent(mock_llm_provider)

        # Configure provider to raise exception
        original_chat = mock_llm_provider.chat

        async def failing_chat(messages, model=None, timeout=None):
            raise RuntimeError("LLM failed")

        mock_llm_provider.chat = failing_chat

        with pytest.raises(RuntimeError):
            await agent.generate(
                messages=[{"role": "user", "content": "X"}],
                session_id="user1"
            )

        # Semaphore must be back to full after the failure
        assert agent._global_semaphore._value == agent._max_concurrency

        # And the agent must still be able to acquire permits (still usable)
        mock_llm_provider.chat = original_chat
        result = await agent.generate(
            messages=[{"role": "user", "content": "Y"}],
            session_id="user2"
        )
        assert result is not None
        assert agent._global_semaphore._value == agent._max_concurrency

    @pytest.mark.asyncio
    async def test_lock_acquisition_order(self, mock_llm_provider):
        """
        Lock acquisition order: Semaphore first, then per-session lock

        This prevents deadlock if two sessions compete for semaphore
        """
        agent = ChatAgent(mock_llm_provider)

        # Drain the semaphore completely so no permits are available
        for _ in range(agent._max_concurrency):
            await agent._global_semaphore.acquire()
        assert agent._global_semaphore._value == 0

        # Start a generate() call: it must block on the SEMAPHORE first.
        # The session lock is created inside the semaphore block, so while
        # the task is blocked there, no session lock may exist yet — this
        # proves the order is semaphore -> session lock (deadlock-safe).
        task = asyncio.ensure_future(
            agent.generate(
                messages=[{"role": "user", "content": "A"}],
                session_id="user1"
            )
        )
        # Give the task a chance to run up to the first await point
        await asyncio.sleep(0.05)

        # The task is blocked on the semaphore: the per-session lock must
        # NOT exist yet (acquisition order is semaphore -> session lock)
        assert "user1" not in agent._session_locks, (
            "session lock acquired before semaphore (deadlock-prone order)"
        )

        # Release the semaphore: the task completes
        agent._global_semaphore.release()
        result = await task
        assert result == "Response"
