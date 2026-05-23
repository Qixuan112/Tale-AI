"""
Prompt section data types for context management.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Any, Optional


@dataclass
class PromptSection:
    """A named, orderable, cache-tagged fragment of the system prompt."""

    name: str
    content: str = ""
    cacheable: bool = False
    order: int = 0
    description: str = ""
    _content_provider: Optional[Callable[[], str]] = field(default=None, repr=False)

    def render(self) -> str:
        """Resolve content — calls provider if set, otherwise returns static content."""
        if self._content_provider is not None:
            return self._content_provider()
        return self.content


@dataclass
class CachedPrompt:
    """Separated cacheable prefix and dynamic suffix for multi-message caching.

    cacheable_prefix: all static sections concatenated — stays byte-identical across
        requests and can be placed in a standalone system message that hits the cache.
    dynamic_suffix: all dynamic sections concatenated — changes per call,
        placed in a separate system message or prepended to the first user message.
    """

    cacheable_prefix: str
    dynamic_suffix: str
    sections_metadata: List[Dict[str, Any]] = field(default_factory=list)
