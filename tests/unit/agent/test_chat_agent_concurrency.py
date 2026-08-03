"""
Unit tests for ChatAgent concurrency control

**CRITICAL TESTS** - These verify the fix for issue #1 (global lock problem)
Tests MUST pass to prove per-session lock + semaphore work correctly.
"""
import pytest
import asyncio
import time
from typing import List, Dict
from unittest.mock import AsyncMock, MagicMock

from core.agent import ChatAgent


@pytest.fixture
def mock_llm_provider_slow():
    """Mock LLM provider with configurable delay"""
    provider = AsyncMock()

    async def mock_chat(messages, model=None, timeout=None):
        """Simulate slow LLM call (1 second)"""
        await asyncio.sleep(1.0)
        # Return different responses to verify call order
        last_user_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), 'unknown')
        return f"Response to: {last_user_msg}"

    provider.chat = mock_chat
    return provider


class TestChatAgentConcurrency:
    """Test ChatAgent per-session lock and semaphore (CRITICAL for issue #1)"""

    @pytest.mark.asyncio
    async def test_different_sessions_run_concurrently(self, mock_llm_provider_slow):
        """
        CRITICAL: Different sessions should run in parallel, not blocked by global lock

        Issue #1 problem: All sessions blocked by single _chat_lock
        Expected fix: Per-session lock allows concurrent execution

        Test: 3 different users send messages simultaneously
        Expected: Total time ~1s (concurrent), NOT 3s (serial)
        """
        agent = ChatAgent(mock_llm_provider_slow)

        start_time = time.time()

        # Three concurrent calls with different session_ids
        tasks = [
            agent.generate(
                messages=[{"role": "user", "content": f"U{i}"}],
                session_id=f"user{i}",
                timeout=60.0
            )
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        # Should complete in ~1s (concurrent), not ~3s (serial)
        # Allow 0.5s tolerance for overhead
        assert elapsed < 1.5, f"Concurrent execution took {elapsed:.2f}s, expected <1.5s"
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_same_session_runs_serially(self, mock_llm_provider_slow):
        """
        CRITICAL: Same session messages must be strictly serial

        Per-session lock ensures message order within one conversation

        Test: Same user sends 3 messages rapidly
        Expected: Processed in strict order, total time ~3s (serial)
        """
        agent = ChatAgent(mock_llm_provider_slow)

        start_time = time.time()

        # Three serial calls with SAME session_id
        responses = []
        for i in range(3):
            resp = await agent.generate(
                messages=[{"role": "user", "content": f"Message {i}"}],
                session_id="user1",
                timeout=60.0
            )
            responses.append(resp)

        elapsed = time.time() - start_time

        # Should take ~3s (serial execution)
        assert elapsed >= 2.5, f"Serial execution took {elapsed:.2f}s, expected ≥2.5s"
        assert elapsed < 3.5, f"Serial execution took {elapsed:.2f}s, expected <3.5s"

        # Verify responses are in correct order
        assert "Message 0" in responses[0]
        assert "Message 1" in responses[1]
        assert "Message 2" in responses[2]

    @pytest.mark.asyncio
    async def test_semaphore_limits_max_concurrency(self, mock_llm_provider_slow):
        """
        CRITICAL: Semaphore should limit max concurrent LLM calls

        Even with per-session locks, we need global rate limiting

        Test: 5 different users send messages simultaneously
        With Semaphore(3): First 3 run (1s), next 2 queued (2s total)
        Expected: Total time ~2s
        """
        agent = ChatAgent(mock_llm_provider_slow, max_concurrency=3)

        start_time = time.time()

        # Five concurrent calls, different sessions
        tasks = [
            agent.generate(
                messages=[{"role": "user", "content": f"U{i}"}],
                session_id=f"user{i}",
                timeout=60.0
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        # Should take ~2s (two waves: 3 + 2)
        assert elapsed >= 1.8, f"Semaphore test took {elapsed:.2f}s, expected ≥1.8s"
        assert elapsed < 2.5, f"Semaphore test took {elapsed:.2f}s, expected <2.5s"
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_mixed_concurrent_and_serial(self, mock_llm_provider_slow):
        """
        COMPLEX: Mix of same-session serial and different-session concurrent

        User1 sends 2 messages (serial)
        User2 sends 1 message (concurrent with User1's first)

        Expected timeline:
        t=0s: User1-Msg1 starts, User2-Msg1 starts (concurrent)
        t=1s: Both complete
        t=1s: User1-Msg2 starts (serial wait)
        t=2s: User1-Msg2 completes
        Total: ~2s
        """
        agent = ChatAgent(mock_llm_provider_slow)

        start_time = time.time()

        # User1 sends 2 messages (will be serial due to same session_id)
        # User2 sends 1 message (concurrent with User1's first)
        async def user1_workflow():
            await agent.generate(
                messages=[{"role": "user", "content": "M1"}],
                session_id="user1",
                timeout=60.0
            )
            await agent.generate(
                messages=[{"role": "user", "content": "M2"}],
                session_id="user1",
                timeout=60.0
            )

        async def user2_workflow():
            await agent.generate(
                messages=[{"role": "user", "content": "M1"}],
                session_id="user2",
                timeout=60.0
            )

        await asyncio.gather(user1_workflow(), user2_workflow())

        elapsed = time.time() - start_time

        # User1-Msg1 and User2-Msg1 concurrent (1s)
        # User1-Msg2 serial after (1s)
        # Total: ~2s
        assert elapsed >= 1.8 and elapsed < 2.5, (
            f"Mixed workload took {elapsed:.2f}s, expected 1.8-2.5s"
        )

    @pytest.mark.asyncio
    async def test_lock_cleanup_on_error(self, mock_llm_provider_slow):
        """
        Per-session locks must be released even if LLM call fails

        If lock is not released, the session will be permanently blocked
        """
        agent = ChatAgent(mock_llm_provider_slow)

        # Save original provider before swapping in the failing one
        original_chat = mock_llm_provider_slow.chat

        # Configure provider to raise exception
        async def failing_chat(messages, model=None, timeout=None):
            raise RuntimeError("LLM failed")

        mock_llm_provider_slow.chat = failing_chat

        # First call should fail and release lock
        with pytest.raises(RuntimeError):
            await agent.generate(
                messages=[{"role": "user", "content": "X"}],
                session_id="user1",
                timeout=60.0
            )

        # Second call should still work (lock was released)
        mock_llm_provider_slow.chat = original_chat
        result = await agent.generate(
            messages=[{"role": "user", "content": "Y"}],
            session_id="user1",
            timeout=60.0
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_session_lock_isolation(self, mock_llm_provider_slow):
        """
        Verify each session has its own lock instance

        Locks should not be shared across sessions
        """
        agent = ChatAgent(mock_llm_provider_slow)

        await agent.generate(
            messages=[{"role": "user", "content": "A"}],
            session_id="user1",
            timeout=60.0
        )
        await agent.generate(
            messages=[{"role": "user", "content": "B"}],
            session_id="user2",
            timeout=60.0
        )

        # Each session must have an independent lock instance
        assert agent._session_locks["user1"] is not agent._session_locks["user2"]
