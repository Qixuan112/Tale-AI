from .config import MAX_CONTEXT, MAX_SPLIT_COUNT
from .provide import (
    CHAT_API_KEY, CHAT_MODEL, CHAT_URL,
    PLAN_API_KEY, PLAN_MODEL, PLAN_URL,
    TOOL_API_KEY, TOOL_MODEL, TOOL_URL,
    provide_config,
    get_chat_api_key, get_chat_model, get_chat_url,
    get_plan_api_key, get_plan_model, get_plan_url,
    get_tool_api_key, get_tool_model, get_tool_url,
    get_config, reload_config,
)
from .model import (
    CharacterConfig, ProviderConfig, ModelMapping, ModelsConfig,
    BotBehaviorConfig, ContextConfig, SelfieConfig, BotConfig,
    AdapterConfig, AdaptersConfig, PersonaConfig, ProvideConfig,
)
from .loader import config_loader

# 提示词 —— 懒加载以避免循环导入
CHAT_PROMPT = None
PLAN_PROMPT = None
TOOL_PROMPT = None


def _load_prompts():
    """加载提示词（保持向后兼容）"""
    global CHAT_PROMPT, PLAN_PROMPT, TOOL_PROMPT
    if CHAT_PROMPT is None:
        from .prompt import get_chat_prompt as _gcp, format_plan_prompt as _fpp
        CHAT_PROMPT = _gcp()
        PLAN_PROMPT = _fpp()
        from .prompt import TOOL_PROMPT as _tp
        TOOL_PROMPT = _tp


def get_chat_prompt():
    """获取聊天提示词（始终最新）"""
    from .prompt import get_chat_prompt as _gcp
    return _gcp()
