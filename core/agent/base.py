"""
Abstract base class for LLM agents

Defines the contract that all LLM agents must implement.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class LLMAgent(ABC):
    """Abstract base class for all LLM agents

    All agents are stateless - conversation history is passed as parameter,
    not stored internally. This allows multiple sessions to share one agent
    instance safely.
    """

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict],
        session_id: str,
        timeout: Optional[float] = 60.0
    ) -> str:
        """Generate LLM response

        Args:
            messages: Conversation history (list of {role, content} dicts)
            session_id: Session identifier for per-session locking
            timeout: Timeout in seconds (default 60s)

        Returns:
            LLM response string

        Raises:
            asyncio.TimeoutError: If LLM call exceeds timeout
        """
        pass

    @abstractmethod
    def get_config(self) -> dict:
        """Get agent configuration

        Returns:
            Configuration dictionary
        """
        pass
