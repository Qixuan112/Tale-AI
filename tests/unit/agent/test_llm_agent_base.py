"""
Unit tests for LLMAgent abstract base class

Tests the abstract interface and contract that all LLM agents must implement.
"""
import pytest
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from core.agent import LLMAgent, ChatAgent


class TestLLMAgentInterface:
    """Test LLMAgent abstract base class interface"""

    def test_llm_agent_is_abstract(self):
        """LLMAgent should be an abstract base class"""
        assert issubclass(LLMAgent, ABC)

        # Cannot instantiate directly (abstract generate + get_config)
        with pytest.raises(TypeError):
            LLMAgent()

    def test_generate_method_required(self):
        """All LLM agents must implement generate() method"""
        import inspect

        # Abstract methods must be implemented by concrete agents
        assert "generate" in LLMAgent.__abstractmethods__

        # ChatAgent must be concrete (not abstract) and implement generate
        assert not inspect.isabstract(ChatAgent), "ChatAgent is still abstract"
        assert callable(ChatAgent.generate)

    def test_agent_must_be_stateless(self):
        """LLM agents should not maintain conversation state internally"""
        # History should be passed as parameter, not stored in agent
        # This allows multiple sessions to share one agent instance safely
        import inspect

        sig = inspect.signature(LLMAgent.generate)
        params = list(sig.parameters.keys())
        assert "messages" in params, "generate() must accept messages parameter"
        assert "session_id" in params, "generate() must accept session_id parameter"
        assert "self" in params

        # The agent must NOT have a _messages attribute
        agent = ChatAgent(None)
        assert not hasattr(agent, "_messages")

    def test_timeout_parameter_contract(self):
        """All generate() calls must accept timeout parameter"""
        import inspect

        sig = inspect.signature(LLMAgent.generate)
        timeout_param = sig.parameters["timeout"]
        # Default timeout should be 60 seconds
        assert timeout_param.default == 60.0, (
            f"Default timeout is {timeout_param.default}, expected 60.0"
        )
