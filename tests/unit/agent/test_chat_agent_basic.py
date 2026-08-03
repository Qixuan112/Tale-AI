"""
Unit tests for ChatAgent basic functionality

Tests core ChatAgent behavior without concurrency concerns.
"""
import pytest
import asyncio
import time
from typing import List, Dict
from unittest.mock import AsyncMock, MagicMock

from core.agent import ChatAgent


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider that returns fixed responses with delay"""
    provider = AsyncMock()

    async def mock_chat(messages, model=None, timeout=None):
        """Simulate LLM call with 0.1s delay"""
        await asyncio.sleep(0.1)
        return "Mock LLM response"

    provider.chat = mock_chat
    return provider


@pytest.fixture
def mock_session_manager():
    """Mock session manager"""
    manager = MagicMock()
    manager.get_memory.return_value = []
    manager.get_session.return_value = MagicMock(enabled=True)
    return manager


class TestChatAgentBasic:
    """Test ChatAgent basic functionality (no concurrency)"""

    @pytest.mark.asyncio
    async def test_generate_returns_response(self, mock_llm_provider):
        """generate() should return LLM response"""
        agent = ChatAgent(mock_llm_provider)
        result = await agent.generate(
            messages=[{"role": "user", "content": "Hello"}],
            session_id="user1"
        )
        assert result == "Mock LLM response"

    @pytest.mark.asyncio
    async def test_agent_is_stateless(self, mock_llm_provider):
        """ChatAgent should not store conversation history"""
        agent = ChatAgent(mock_llm_provider)
        await agent.generate(
            messages=[{"role": "user", "content": "Hi"}],
            session_id="user1"
        )
        # History is passed per call; the agent keeps no conversation state
        assert not hasattr(agent, "_messages")
        assert not hasattr(agent, "_history")

    @pytest.mark.asyncio
    async def test_timeout_parameter_passed(self, mock_llm_provider):
        """Timeout parameter should be enforced on provider calls (issue #6)"""
        agent = ChatAgent(mock_llm_provider)

        # Normal call with a generous timeout succeeds
        result = await agent.generate(
            messages=[{"role": "user", "content": "Hi"}],
            session_id="user1",
            timeout=5.0
        )
        assert result == "Mock LLM response"

        # A call that exceeds the timeout must be aborted promptly
        async def hang(messages, model=None, timeout=None):
            await asyncio.sleep(100)

        mock_llm_provider.chat = hang
        start = time.time()
        with pytest.raises(asyncio.TimeoutError):
            await agent.generate(
                messages=[{"role": "user", "content": "Hi"}],
                session_id="user2",
                timeout=0.2
            )
        # Must raise after ~0.2s, not hang for the full 100s
        assert time.time() - start < 5.0

    @pytest.mark.asyncio
    async def test_messages_format_preserved(self, mock_llm_provider):
        """Messages list format should be passed to provider unchanged"""
        received = {}

        async def capture(messages, model=None, timeout=None):
            received["messages"] = messages
            return "Mock LLM response"

        mock_llm_provider.chat = capture
        agent = ChatAgent(mock_llm_provider)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        await agent.generate(messages=messages, session_id="user1")

        # Provider must receive the exact messages passed by the caller
        assert received.get("messages") == messages
