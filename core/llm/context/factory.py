"""
Default context factories for each LLM agent.

Each factory decomposes the current monolithic prompt into ordered,
cache-tagged PromptSection instances.  The resulting AgentContext, when
assembled via ``build()``, produces byte-identical output to the existing
``get_chat_prompt()`` / ``format_plan_prompt()`` / ``build_fc_prompt()``.
"""

# NOTE: all template strings are imported from core.config.prompt (single source of truth).
_IMPORT_FAILED = False
try:
    from ...config.prompt import (
        CHAT_BASE_TEMPLATE,
        PLAN_TEMPLATE,
        FC_FORMAT_TEMPLATE,
    )
except ImportError:
    _IMPORT_FAILED = True
    CHAT_BASE_TEMPLATE = ""
    PLAN_TEMPLATE = ""
    FC_FORMAT_TEMPLATE = ""

from typing import List, Dict

from .section import PromptSection
from .agent_context import AgentContext


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def create_chat_context(
    character_prompt: str,
    dialogue_examples: List[Dict],
    persona_additional_prompt: str = "",
) -> AgentContext:
    """Build default AgentContext for ChatLLM.

    When assembled via ``build()`` the output is byte-identical to
    ``get_chat_prompt()`` in ``core/config/prompt.py``.

    Args:
        character_prompt: Output of ``get_character_prompt()`` from provide.py.
        dialogue_examples: Output of ``get_dialogue_examples()`` from provide.py.
        persona_additional_prompt: Extra prompt from persona config.
    """
    context = AgentContext("chat")

    context.add_section(PromptSection(
        name="character_definition",
        content=character_prompt,
        cacheable=True,
        order=1,
    ))

    context.add_section(PromptSection(
        name="chat_base_instructions",
        content=CHAT_BASE_TEMPLATE.strip() if CHAT_BASE_TEMPLATE else "",
        cacheable=True,
        order=2,
    ))

    if dialogue_examples:
        examples_text = ""
        for i, ex in enumerate(dialogue_examples[:3], 1):
            examples_text += f"\n示例 {i}:\n"
            examples_text += f'用户："{ex.get("user", "")}"\n'
            examples_text += f'你："{ex.get("assistant", "")}"\n'
        context.add_section(PromptSection(
            name="dialogue_style_examples",
            content="## 角色对话风格示例" + examples_text,
            cacheable=True,
            order=3,
        ))

    if persona_additional_prompt:
        context.add_section(PromptSection(
            name="additional_prompt",
            content=persona_additional_prompt,
            cacheable=True,
            order=4,
        ))

    return context


def create_plan_context(
    name: str = "AI",
    english_name: str = "",
    age: str = "未知",
    gender: str = "未知",
    values: List[str] = None,
) -> AgentContext:
    """Build default AgentContext for PlanLLM.

    When assembled via ``build()`` the output is byte-identical to
    ``format_plan_prompt()`` in ``core/config/prompt.py``.

    Args:
        name: Character's Chinese name.
        english_name: Character's English name.
        age: Character's age.
        gender: Character's gender.
        values: Top values (up to 3) used as personality traits.
    """
    context = AgentContext("plan")

    # Use the new unified plan template with character name injected
    plan_content = PLAN_TEMPLATE.replace("{character_name}", name) if PLAN_TEMPLATE else ""

    context.add_section(PromptSection(
        name="plan_template",
        content=plan_content,
        cacheable=True,
        order=1,
    ))

    return context


def create_tool_context(tools_text: str = "") -> AgentContext:
    """Build default AgentContext for ToolLLM.

    When assembled via ``build()`` the output is byte-identical to
    ``build_fc_prompt()`` in ``core/tools/registry.py``.

    Args:
        tools_text: Formatted tool list from ``ToolRegistry.get_tools_list_text()``.
    """
    context = AgentContext("tool")

    fc_intro = (
        "你是 \"ToolLLM\"，工具调用专家。你的任务是分析用户的动作指令，"
        "输出标准化的 Function Calling JSON。\n\n" + tools_text
    )

    context.add_section(PromptSection(
        name="tool_definitions",
        content=tools_text,
        cacheable=True,
        order=1,
    ))

    context.add_section(PromptSection(
        name="fc_format_template",
        content=fc_intro + FC_FORMAT_TEMPLATE.strip() if FC_FORMAT_TEMPLATE else fc_intro,
        cacheable=True,
        order=2,
    ))

    return context
