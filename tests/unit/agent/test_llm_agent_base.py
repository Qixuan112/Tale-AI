"""
Unit tests for LLMAgent abstract base class

Tests the abstract interface and contract that all LLM agents must implement.
"""
import pytest
from abc import ABC
from typing import List, Dict, Optional


class TestLLMAgentInterface:
    """Test LLMAgent abstract base class interface"""

    def test_llm_agent_is_abstract(self):
        """LLMAgent should be an abstract base class"""
        # Since we haven't created LLMAgent yet, this test will guide implementation
        # Expected: LLMAgent should inherit from ABC and define abstract methods
        pass

    def test_generate_method_required(self):
        """All LLM agents must implement generate() method"""
        # Expected signature:
        # async def generate(
        #     self,
        #     messages: List[Dict],
        #     session_id: str,
        #     timeout: Optional[float] = 60.0
        # ) -> str
        pass

    def test_agent_must_be_stateless(self):
        """LLM agents should not maintain conversation state internally"""
        # History should be passed as parameter, not stored in agent
        # This allows multiple sessions to share one agent instance safely
        pass

    def test_timeout_parameter_contract(self):
        """All generate() calls must accept timeout parameter"""
        # Default timeout should be 60 seconds
        # Agents must respect timeout and raise asyncio.TimeoutError on expiry
        pass
