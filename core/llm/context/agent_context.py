"""
AgentContext — per-agent prompt section registry and assembler.
"""
from typing import Dict, List, Optional

from .section import PromptSection, CachedPrompt


class AgentContext:
    """Holds and assembles prompt sections for a single LLM agent.

    Two assembly modes:
    - ``build()`` — single concatenated string (backward compatible).
    - ``build_messages_head(cache_strategy)`` — list of message dicts suitable
      for prepending to the messages array. When cache_strategy is "multi_message",
      static and dynamic sections go into separate system messages so the static
      prefix stays byte-identical and hits the provider's prompt cache.
    """

    def __init__(self, agent_name: str, sections: Optional[List[PromptSection]] = None):
        self.agent_name = agent_name
        self._sections: Dict[str, PromptSection] = {}
        if sections:
            for s in sections:
                self.add_section(s)

    # ------------------------------------------------------------------
    # Section management
    # ------------------------------------------------------------------

    def add_section(self, section: PromptSection) -> None:
        self._sections[section.name] = section

    def get_section(self, name: str) -> Optional[PromptSection]:
        return self._sections.get(name)

    def remove_section(self, name: str) -> None:
        self._sections.pop(name, None)

    def set_section_content(self, name: str, content: str) -> None:
        """Update the static content of an existing section at runtime."""
        if name in self._sections:
            self._sections[name].content = content

    def reorder(self, order_map: Dict[str, int]) -> None:
        """Bulk-update order values from {name: new_order}."""
        for name, order in order_map.items():
            if name in self._sections:
                self._sections[name].order = order

    @property
    def sections(self) -> List[PromptSection]:
        return sorted(self._sections.values(), key=lambda s: s.order)

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def build(self, cache_optimize: bool = True) -> str:
        """Assemble all sections into a single system prompt string.

        When *cache_optimize* is True (default), cacheable sections are placed first
        in their configured order, then non-dynamic sections. Dynamic sections are
        excluded (they should be injected into user messages via get_dynamic_reminder).
        When False, sections are sorted purely by their ``order`` field with no grouping.
        """
        # Filter out dynamic sections (they go in user message)
        static_sections = [s for s in self._sections.values() if not getattr(s, 'dynamic', False)]

        if cache_optimize:
            ordered = sorted(
                static_sections,
                key=lambda s: (0 if s.cacheable else 1, s.order),
            )
        else:
            ordered = sorted(static_sections, key=lambda s: s.order)

        return "\n".join(s.render() for s in ordered if s.render())

    def build_cached(self) -> CachedPrompt:
        """Return separated cacheable prefix and dynamic suffix.

        The caller decides message placement — e.g. cacheable_prefix as a
        standalone system message, dynamic_suffix as another system message
        or prepended to the first user message.

        Note: Sections marked with dynamic=True are excluded entirely and should
        be injected via get_dynamic_reminder() into user messages.
        """
        # Filter out dynamic sections (they go in user message)
        non_dynamic = [s for s in self._sections.values() if not getattr(s, 'dynamic', False)]

        cacheable = sorted(
            [s for s in non_dynamic if s.cacheable],
            key=lambda s: s.order,
        )
        non_cacheable = sorted(
            [s for s in non_dynamic if not s.cacheable],
            key=lambda s: s.order,
        )

        cacheable_prefix = "\n".join(s.render() for s in cacheable if s.render())
        dynamic_suffix = "\n".join(s.render() for s in non_cacheable if s.render())

        metadata = [
            {
                "name": s.name,
                "cacheable": s.cacheable,
                "char_count": len(s.render()),
            }
            for s in self._sections.values()
        ]

        return CachedPrompt(
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
            sections_metadata=metadata,
        )

    def build_messages_head(self, cache_strategy: str = "single_message") -> List[Dict[str, str]]:
        """Return message dicts for the head of a messages array.

        ``"single_message"`` (default, backward-compatible):
            Returns a single system message with all sections concatenated.

        ``"multi_message"``:
            Returns two system messages — the first containing only cacheable
            sections (byte-identical across calls, hits the prompt cache),
            the second containing only dynamic sections.

            When there are no dynamic sections the second message is omitted.
        """
        if cache_strategy == "multi_message":
            cached = self.build_cached()
            head: List[Dict[str, str]] = []
            if cached.cacheable_prefix:
                head.append({"role": "system", "content": cached.cacheable_prefix})
            if cached.dynamic_suffix:
                head.append({"role": "system", "content": cached.dynamic_suffix})
            return head if head else [{"role": "system", "content": ""}]

        # Default: single message (backward compatible)
        return [{"role": "system", "content": self.build()}]

    def get_dynamic_reminder(self) -> str:
        """Extract dynamic sections for injection into user message.

        Returns a <system_reminder> block containing all dynamic sections,
        or empty string if no dynamic sections exist.
        """
        dynamic_sections = sorted(
            [s for s in self._sections.values() if getattr(s, 'dynamic', False)],
            key=lambda s: s.order,
        )

        if not dynamic_sections:
            return ""

        dynamic_content = "\n".join(s.render() for s in dynamic_sections if s.render())
        if not dynamic_content:
            return ""

        return f"<system_reminder>\n{dynamic_content}\n</system_reminder>"

    def get_system_message(self) -> Dict[str, str]:
        """Convenience: returns a single ``{"role": "system", "content": ...}`` dict."""
        return {"role": "system", "content": self.build()}

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_config(self) -> List[Dict]:
        return [
            {
                "name": s.name,
                "cacheable": s.cacheable,
                "order": s.order,
                "description": s.description,
            }
            for s in self._sections.values()
        ]
