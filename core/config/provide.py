"""
配置系统公共接口
=================
保持向后兼容的薄重导出层。
"""

import os
from typing import Dict, List, Any, Optional

from .model import (
    CharacterConfig,
    ProviderConfig,
    ModelMapping,
    ModelsConfig,
    BotBehaviorConfig,
    ContextConfig,
    SelfieConfig,
    BotConfig,
    AdapterConfig,
    AdaptersConfig,
    PersonaConfig,
    ProvideConfig,
)
from .loader import ConfigLoader, config_loader, provide_config

# ============ 提示词生成 ============


def get_character_prompt() -> str:
    """根据 character.yaml 生成角色提示词"""
    cfg = config_loader.persona
    char = cfg.character

    prompt_parts = []

    prompt_parts.append(f"你是 \"{char.ChineseName}\"（{char.EnglishName}），一个数字生命。")

    if char.NickNames:
        prompt_parts.append(f"用户也可以称呼你为：{', '.join(char.NickNames)}")

    prompt_parts.append("")

    prompt_parts.append("## 基本信息")
    prompt_parts.append(f"- 性别：{char.gender}")
    prompt_parts.append(f"- 年龄：{char.age}岁")
    if char.birthday:
        prompt_parts.append(f"- 生日：{char.birthday}")
    prompt_parts.append("")

    if char.appearance:
        prompt_parts.append("## 外貌描述")
        prompt_parts.append(char.appearance)
        prompt_parts.append("")

    if char.language:
        prompt_parts.append("## 语言能力")
        if isinstance(char.language, dict):
            primary = char.language.get("primary", "")
            style = char.language.get("style", "")
            if primary:
                prompt_parts.append(f"- 主要语言：{primary}")
            if style:
                prompt_parts.append(f"- 语言风格：{style}")
        else:
            prompt_parts.append(str(char.language))
        prompt_parts.append("")

    if char.views:
        prompt_parts.append("## 世界观")
        prompt_parts.append(char.views)
        prompt_parts.append("")

    if char.values:
        prompt_parts.append("## 价值观")
        for value in char.values:
            prompt_parts.append(f"- {value}")
        prompt_parts.append("")

    if char.hobbies:
        prompt_parts.append("## 兴趣爱好")
        for hobby in char.hobbies:
            prompt_parts.append(f"- {hobby}")
        prompt_parts.append("")

    if char.expressions:
        prompt_parts.append("## 常用表达方式")
        for key, value in char.expressions.items():
            prompt_parts.append(f"- {key}：{value}")
        prompt_parts.append("")

    if char.dialogue_style_imitation:
        prompt_parts.append("## 对话风格示例")
        prompt_parts.append("请参考以下示例来模仿我的对话风格：")
        prompt_parts.append("")
        for example in char.dialogue_style_imitation:
            if isinstance(example, dict):
                user_msg = example.get("user", "")
                assistant_msg = example.get("assistant", "")
                if user_msg and assistant_msg:
                    prompt_parts.append(f"用户：{user_msg}")
                    prompt_parts.append(f"你：{assistant_msg}")
                    prompt_parts.append("")
            elif isinstance(example, str) and example:
                prompt_parts.append(f"示例：{example}")
                prompt_parts.append("")

    if cfg.additional_prompt:
        prompt_parts.append(cfg.additional_prompt)
        prompt_parts.append("")

    if cfg.additional_examples:
        prompt_parts.append("## 更多对话示例")
        for example in cfg.additional_examples:
            user_msg = example.get("user", "")
            assistant_msg = example.get("assistant", "")
            if user_msg and assistant_msg:
                prompt_parts.append(f"用户：{user_msg}")
                prompt_parts.append(f"你：{assistant_msg}")
                prompt_parts.append("")

    return "\n".join(prompt_parts)


def get_dialogue_examples() -> List[Dict[str, str]]:
    """获取对话示例列表"""
    cfg = config_loader.persona
    examples = []

    if cfg.character.dialogue_style_imitation:
        for item in cfg.character.dialogue_style_imitation:
            if isinstance(item, dict):
                examples.append(item)
            elif isinstance(item, str):
                examples.append({"user": item, "assistant": ""})

    if cfg.additional_examples:
        for example in cfg.additional_examples:
            if isinstance(example, dict):
                examples.append(example)

    return examples


# ============ 便捷函数 ============


def get_config() -> ProvideConfig:
    return config_loader.config


def reload_config():
    global CHAT_API_KEY, CHAT_MODEL, CHAT_URL
    global PLAN_API_KEY, PLAN_MODEL, PLAN_URL
    global TOOL_API_KEY, TOOL_MODEL, TOOL_URL
    config_loader.reload()
    CHAT_API_KEY = get_chat_api_key()
    CHAT_MODEL = get_chat_model()
    CHAT_URL = get_chat_url()
    PLAN_API_KEY = get_plan_api_key()
    PLAN_MODEL = get_plan_model()
    PLAN_URL = get_plan_url()
    TOOL_API_KEY = get_tool_api_key()
    TOOL_MODEL = get_tool_model()
    TOOL_URL = get_tool_url()


# ============ 环境变量函数（每次调用动态读取） ============


def get_chat_api_key() -> str:
    return os.getenv("TALE_CHAT_API_KEY") or config_loader.chat_api.get("api_key", "")


def get_chat_model() -> str:
    return os.getenv("TALE_CHAT_MODEL") or config_loader.chat_api.get("model", "")


def get_chat_url() -> str:
    return os.getenv("TALE_CHAT_URL") or config_loader.chat_api.get("url", "")


def get_plan_api_key() -> str:
    return os.getenv("TALE_PLAN_API_KEY") or config_loader.plan_api.get("api_key", "")


def get_plan_model() -> str:
    return os.getenv("TALE_PLAN_MODEL") or config_loader.plan_api.get("model", "")


def get_plan_url() -> str:
    return os.getenv("TALE_PLAN_URL") or config_loader.plan_api.get("url", "")


def get_tool_api_key() -> str:
    return os.getenv("TALE_TOOL_API_KEY") or config_loader.tool_api.get("api_key", "")


def get_tool_model() -> str:
    return os.getenv("TALE_TOOL_MODEL") or config_loader.tool_api.get("model", "")


def get_tool_url() -> str:
    return os.getenv("TALE_TOOL_URL") or config_loader.tool_api.get("url", "")


# ============ 向后兼容的模块级常量 ============
# 这些在 import 时求值，不会随配置重载而更新。
# 新代码请使用对应的 get_*() 函数。

CHAT_API_KEY = get_chat_api_key()
CHAT_MODEL = get_chat_model()
CHAT_URL = get_chat_url()

PLAN_API_KEY = get_plan_api_key()
PLAN_MODEL = get_plan_model()
PLAN_URL = get_plan_url()

TOOL_API_KEY = get_tool_api_key()
TOOL_MODEL = get_tool_model()
TOOL_URL = get_tool_url()
