from .config import MAX_CONTEXT, MAX_SPLIT_COUNT 
from .provide import (
    CHAT_API_KEY, CHAT_MODEL, CHAT_URL,
    PLAN_API_KEY, PLAN_MODEL, PLAN_URL,
    TOOL_API_KEY, TOOL_MODEL, TOOL_URL,
    provide_config
)

# 提示词变量 - 延迟加载以避免循环导入
CHAT_PROMPT = None
PLAN_PROMPT = None
TOOL_PROMPT = None

def _load_prompts():
    """加载提示词"""
    global CHAT_PROMPT, PLAN_PROMPT, TOOL_PROMPT
    if CHAT_PROMPT is None:
        from .prompt import CHAT_PROMPT as _cp, PLAN_PROMPT as _pp, TOOL_PROMPT as _tp
        CHAT_PROMPT = _cp
        PLAN_PROMPT = _pp
        TOOL_PROMPT = _tp

def get_chat_prompt():
    """获取聊天提示词"""
    _load_prompts()
    from .prompt import get_chat_prompt as _gcp
    return _gcp()





