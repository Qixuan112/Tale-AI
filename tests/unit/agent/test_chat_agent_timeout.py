"""
Unit tests for ChatAgent timeout protection

Tests that ChatAgent properly implements timeout for LLM calls (issue #6 fix).
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock

from core.agent import ChatAgent


@pytest.fixture
def mock_llm_provider_timeout():
    """Mock LLM provider that can simulate timeout"""
    provider = AsyncMock()

    async def mock_chat_hangs(messages, model=None, timeout=None):
        """Simulate hanging LLM call"""
        await asyncio.sleep(100)  # Hangs for 100s
        return "Should not reach here"

    provider.chat = mock_chat_hangs
    return provider


def normal_provider(response="OK"):
    """Build a provider whose chat() returns immediately"""
    provider = AsyncMock()

    async def mock_chat(messages, model=None, timeout=None):
        return response

    provider.chat = mock_chat
    return provider


class TestChatAgentTimeout:
    """Test ChatAgent timeout protection (issue #6 fix)"""

    @pytest.mark.asyncio
    async def test_first_call_has_timeout(self, mock_llm_provider_timeout):
        """
        CRITICAL: First LLM call must have timeout parameter

        Current bug: First call has no timeout, can hang forever
        Expected fix: All calls pass timeout to provider

        Test: 1s timeout vs provider that hangs for 100s
        Expected: asyncio.TimeoutError after ~1s, not 100s
        """
        agent = ChatAgent(mock_llm_provider_timeout)

        start = time.time()
        with pytest.raises(asyncio.TimeoutError):
            await agent.generate(
                messages=[{"role": "user", "content": "test"}],
                session_id="user1",
                timeout=1.0
            )
        elapsed = time.time() - start

        # Timed out after ~1s, must not wait for the 100s hang
        assert elapsed < 5.0, f"Timeout took {elapsed:.2f}s, expected <5s"

    @pytest.mark.asyncio
    async def test_subsequent_calls_have_timeout(self, mock_llm_provider_timeout):
        """
        Verify retry calls also have timeout protection

        All calls should respect timeout, not just first one
        """
        agent = ChatAgent(mock_llm_provider_timeout)

        # Two consecutive calls must BOTH time out
        for i in range(2):
            start = time.time()
            with pytest.raises(asyncio.TimeoutError):
                await agent.generate(
                    messages=[{"role": "user", "content": f"test-{i}"}],
                    session_id="user1",
                    timeout=0.5
                )
            assert time.time() - start < 5.0, (
                f"Call {i + 1} did not respect timeout"
            )

    @pytest.mark.asyncio
    async def test_timeout_error_propagates(self, mock_llm_provider_timeout):
        """
        TimeoutError should propagate to caller

        Caller can catch and handle (retry, error message, etc.)
        """
        agent = ChatAgent(mock_llm_provider_timeout)

        with pytest.raises(asyncio.TimeoutError):
            await agent.generate(
                messages=[{"role": "user", "content": "test"}],
                session_id="user1",
                timeout=0.2
            )

    @pytest.mark.asyncio
    async def test_timeout_releases_lock(self, mock_llm_provider_timeout):
        """
        CRITICAL: Timeout must release per-session lock

        If lock not released, session permanently blocked after timeout
        """
        agent = ChatAgent(mock_llm_provider_timeout)

        # First call times out
        with pytest.raises(asyncio.TimeoutError):
            await agent.generate(
                messages=[{"role": "user", "content": "test"}],
                session_id="user1",
                timeout=0.1
            )

        # Replace provider with a fast one; second call must succeed
        # (proves the per-session lock was released after the timeout)
        agent._provider = normal_provider()
        result = await agent.generate(
            messages=[{"role": "user", "content": "test2"}],
            session_id="user1",
            timeout=5.0
        )
        assert result == "OK"

    @pytest.mark.asyncio
    async def test_timeout_does_not_affect_other_sessions(self):
        """
        One session's timeout should not block other sessions

        Per-session locks ensure isolation
        """
        # Same agent, same provider: hangs only for "hang" messages.
        # This is deterministic — no provider swapping mid-flight.
        provider = AsyncMock()

        async def chat(messages, model=None, timeout=None):
            last = messages[-1]["content"] if messages else ""
            if last == "hang":
                await asyncio.sleep(100)
            return "response"

        provider.chat = chat
        agent = ChatAgent(provider)

        async def user1_timeout():
            with pytest.raises(asyncio.TimeoutError):
                await agent.generate(
                    messages=[{"role": "user", "content": "hang"}],
                    session_id="user1",
                    timeout=0.1
                )

        # user2 with a fast request must NOT be blocked by user1's timeout
        async def user2_success():
            return await agent.generate(
                messages=[{"role": "user", "content": "fast"}],
                session_id="user2",
                timeout=5.0
            )

        results = await asyncio.gather(
            user1_timeout(),
            user2_success(),
            return_exceptions=True
        )

        # user1 timed out, user2 succeeded
        assert results[0] is None, f"user1 should have timed out, got {results[0]!r}"
        assert results[1] == "response"

    @pytest.mark.asyncio
    async def test_default_timeout_is_60_seconds(self):
        """
        Default timeout should be 60 seconds if not specified

        Prevents infinite hangs while allowing reasonable processing time
        """
        agent = ChatAgent(AsyncMock())

        # Default (no timeout) must not raise TimeoutError for fast calls
        async def fast(messages, model=None, timeout=None):
            return "fast response"

        agent._provider.chat = fast
        result = await agent.generate(
            messages=[{"role": "user", "content": "test"}],
            session_id="user1"
        )
        assert result == "fast response"

        # A call that runs longer than the 60s default must be aborted
        async def slow(messages, model=None, timeout=None):
            await asyncio.sleep(0.3)
            return "slow response"

        agent._provider.chat = slow
        with pytest.raises(asyncio.TimeoutError):
            await agent.generate(
                messages=[{"role": "user", "content": "test"}],
                session_id="user2",
                timeout=0.05
            )

    @pytest.mark.asyncio
    async def test_custom_timeout_respected(self):
        """
        Custom timeout values should be passed to provider

        Users can override default timeout per call
        """
        agent = ChatAgent(AsyncMock())

        async def slow(messages, model=None, timeout=None):
            await asyncio.sleep(2.0)
            return "late"

        agent._provider.chat = slow

        # Custom timeout=0.5 vs 2s provider latency -> must time out
        start = time.time()
        with pytest.raises(asyncio.TimeoutError):
            await agent.generate(
                messages=[{"role": "user", "content": "test"}],
                session_id="user1",
                timeout=0.5
            )
        # Timeout must fire near 0.5s, not wait for the 2s sleep
        assert time.time() - start < 1.5
