"""
配置加载器
===========
多文件 YAML 配置加载器，单例模式。
"""

import os
import threading
import logging
from typing import Dict, List, Any, Optional

import yaml

from .model import (
    CharacterConfig,
    ProviderConfig,
    ModelMapping,
    ModelsConfig,
    BotBehaviorConfig,
    ContextConfig,
    SelfieConfig,
    WakeConfig,
    BotConfig,
    AdapterConfig,
    AdaptersConfig,
    PersonaConfig,
    ProvideConfig,
)


logger = logging.getLogger(__name__)


# ============ Schema Validation ============

_SCHEMAS = {
    "character.yaml": {
        "fields": {
            "character": dict,
            "additional_prompt": str,
            "additional_examples": list,
            "raw_persona": str,
        },
        "required": ["character"],
        "nested": {
            "character": {
                "ChineseName": str,
                "NickNames": list,
                "EnglishName": str,
                "gender": str,
                "age": (str, int),
                "birthday": str,
                "appearance": str,
                "language": dict,
                "views": (str, list),
                "values": list,
                "hobbies": list,
                "expressions": (dict, list),
                "dialogue_style_imitation": list,
            },
        },
    },
    "behavior.yaml": {
        "fields": {"bot": dict, "context": dict, "selfie": dict, "wake": dict},
        "required": [],
        "nested": {
            "bot": {
                "max_memory_length": int,
                "max_message_interval": (int, float),
                "max_buffer_messages": int,
                "min_message_delay": (int, float),
                "max_message_delay": (int, float),
                "typing_speed": (int, float),
                "typing_min_delay": (int, float),
            },
            "context": {
                "max_context": int,
                "memory_enabled": bool,
                "personality_strength": (int, float),
            },
            "selfie": {"path": str},
            "wake": {
                "enable_keyword_wake": bool,
                "waking_keywords": list,
                "enable_quote_wake": bool,
            },
        },
    },
    "services.yaml": {
        "fields": {},
        "required": [],
        "provider_fields": {
            "type": str,
            "format": str,
            "api_key": str,
            "base_url": str,
            "model": str,
            "voice_name": str,
            "timeout": (int, float),
        },
    },
    "routing.yaml": {
        "fields": {k: dict for k in ["main_llm", "plan_llm", "tool_llm", "vlm",
                                      "util_model", "image", "tts", "stt"]},
        "required": [],
        "nested": {k: {"provider": str}
                   for k in ["main_llm", "plan_llm", "tool_llm", "vlm",
                             "util_model", "image", "tts", "stt"]},
    },
    "platforms.yaml": {
        "fields": {},
        "required": [],
        "provider_fields": {
            "enabled": bool,
            "adapter_type": str, "desc": str,
            "ws_url": str, "ws_uri": str, "http_url": str,
            "access_token": str, "ws_token": str, "ws_listen_ip": str,
            "auto_reconnect": bool, "reconnect_interval": (int, float),
            "bot_pid": (str, int), "owner_pid": (str, int),
            "bot_token": str, "bot_uid": (str, int),
            "permission_mode": str,
            "group_allow_list": list, "user_allow_list": list,
            "group_deny_list": list, "user_deny_list": list,
            "waking_keywords": list,
            "listening_bvid": str,
            "listening_interval": (int, float),
            "message_process_interval": (int, float),
            "sessdata": str, "bili_jct": str, "buvid3": str,
            "dedeuserid": str, "ac_time_value": str,
        },
    },
    "plugins.yaml": {
        "fields": {"plugins": dict},
        "required": [],
    },
}


def _type_name(t):
    """Return human-readable type name, handling type tuples."""
    if isinstance(t, type):
        return t.__name__
    if isinstance(t, tuple):
        return "|".join(x.__name__ for x in t)
    return str(t)


def _validate_config(config_name: str, data: dict) -> None:
    """Validate config data against schema, logging warnings.
    Never raises — config still loads with defaults for missing fields.
    """
    schema = _SCHEMAS.get(config_name)
    if schema is None:
        return

    if not isinstance(data, dict):
        logger.warning("[Config] %s: top-level is not a dict (got %s)", config_name, type(data).__name__)
        return

    # Required top-level fields
    for field in schema.get("required", []):
        if field not in data:
            logger.warning("[Config] %s: missing required field '%s'", config_name, field)

    # Unknown top-level keys
    known = schema.get("fields", {})
    if known:
        for key in data:
            if key not in known:
                logger.warning("[Config] %s: unknown top-level key '%s'", config_name, key)

    # Type-check top-level fields
    for field, t in known.items():
        if field in data and t is not None and not isinstance(data[field], t):
            logger.warning("[Config] %s: field '%s' should be %s, got %s",
                          config_name, field, _type_name(t), type(data[field]).__name__)

    # Dynamic provider entries (services.yaml, platforms.yaml)
    provider_fields = schema.get("provider_fields")
    if provider_fields:
        for key, value in data.items():
            if isinstance(value, dict):
                for field, t in provider_fields.items():
                    if field in value and not isinstance(value[field], t):
                        logger.warning("[Config] %s: field '%s.%s' should be %s, got %s",
                                      config_name, key, field, _type_name(t),
                                      type(value[field]).__name__)

    # Nested dict fields
    for parent_key, child_fields in schema.get("nested", {}).items():
        parent = data.get(parent_key)
        if not isinstance(parent, dict):
            continue
        for field, t in child_fields.items():
            if field in parent and t is not None and not isinstance(parent[field], t):
                logger.warning("[Config] %s: field '%s.%s' should be %s, got %s",
                              config_name, parent_key, field, _type_name(t),
                              type(parent[field]).__name__)


class ConfigLoader:
    """多文件配置加载器（单例）"""

    _instance = None
    _config = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._lock = threading.Lock()
            self._data_dir = self._get_data_dir()
            self._plugins_config: dict = {}
            self._load_all_configs()

    def _get_data_dir(self) -> str:
        """获取数据目录路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # core/config -> core -> root
        root_dir = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(root_dir, "data")

    def _load_yaml(self, filename: str) -> dict:
        """加载 YAML 文件"""
        filepath = os.path.join(self._data_dir, filename)

        if not os.path.exists(filepath):
            return {}

        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        _validate_config(os.path.basename(filename), data)
        return data

    def _load_all_configs(self):
        """加载所有配置文件"""
        character_data = self._load_yaml("config/character.yaml")
        services_data = self._load_yaml("config/services.yaml")
        routing_data = self._load_yaml("config/routing.yaml")
        behavior_data = self._load_yaml("config/behavior.yaml")
        platforms_data = self._load_yaml("config/platforms.yaml")

        persona = self._parse_persona(character_data)
        providers = self._parse_providers(services_data)
        models = self._parse_models(routing_data)
        bot = self._parse_bot(behavior_data)
        adapters = self._parse_adapters(platforms_data)

        plugins_data = self._load_yaml("config/plugins.yaml")
        self._plugins_config = plugins_data.get("plugins", {})

        new_config = ProvideConfig(
            persona=persona,
            providers=providers,
            models=models,
            bot=bot,
            adapters=adapters,
        )

        with self._lock:
            self._config = new_config

    def _parse_persona(self, data: dict) -> PersonaConfig:
        """解析角色人设配置"""
        char_data = data.get("character", {})

        views_data = char_data.get("views", "")
        if isinstance(views_data, list):
            views_str = "\n".join([str(v) for v in views_data if v])
        else:
            views_str = str(views_data) if views_data else ""

        expressions_data = char_data.get("expressions", {})
        if isinstance(expressions_data, list):
            expressions_dict = {f"expression_{i}": str(v) for i, v in enumerate(expressions_data) if v}
        elif isinstance(expressions_data, dict):
            expressions_dict = expressions_data
        else:
            expressions_dict = {}

        dialogue_data = char_data.get("dialogue_style_imitation", [])
        dialogue_list = []
        if isinstance(dialogue_data, list):
            for item in dialogue_data:
                if isinstance(item, dict):
                    dialogue_list.append(item)
                elif isinstance(item, str) and item:
                    dialogue_list.append({"user": item, "assistant": ""})

        character = CharacterConfig(
            ChineseName=char_data.get("ChineseName", ""),
            NickNames=char_data.get("NickNames", []),
            EnglishName=char_data.get("EnglishName", ""),
            gender=char_data.get("gender", ""),
            age=char_data.get("age", 0) if char_data.get("age") else 0,
            birthday=char_data.get("birthday", ""),
            appearance=char_data.get("appearance", ""),
            language=char_data.get("language", {}),
            views=views_str,
            values=char_data.get("values", []) if isinstance(char_data.get("values"), list) else [],
            hobbies=char_data.get("hobbies", []) if isinstance(char_data.get("hobbies"), list) else [],
            expressions=expressions_dict,
            dialogue_style_imitation=dialogue_list,
        )

        return PersonaConfig(
            character=character,
            additional_prompt=data.get("additional_prompt", ""),
            additional_examples=data.get("additional_examples", []),
            raw_persona=data.get("raw_persona", ""),
        )

    def _parse_providers(self, data: dict) -> Dict[str, ProviderConfig]:
        """解析服务提供商配置"""
        providers = {}

        for name, config in data.items():
            if isinstance(config, dict):
                known_fields = {"type", "format", "api_key", "base_url", "model", "voice_name", "timeout"}
                extra = {k: v for k, v in config.items() if k not in known_fields}

                providers[name] = ProviderConfig(
                    type=config.get("type", ""),
                    format=config.get("format", ""),
                    api_key=config.get("api_key", ""),
                    base_url=config.get("base_url", ""),
                    model=config.get("model", ""),
                    voice_name=config.get("voice_name", ""),
                    timeout=config.get("timeout", 30),
                    extra=extra,
                )

        return providers

    def _parse_models(self, data: dict) -> ModelsConfig:
        """解析模型选择配置"""
        return ModelsConfig(
            main_llm=ModelMapping(provider=data.get("main_llm", {}).get("provider", "")),
            plan_llm=ModelMapping(provider=data.get("plan_llm", {}).get("provider", "")),
            tool_llm=ModelMapping(provider=data.get("tool_llm", {}).get("provider", "")),
            vlm=ModelMapping(provider=data.get("vlm", {}).get("provider", "")),
            util_model=ModelMapping(provider=data.get("util_model", {}).get("provider", "")),
            image=ModelMapping(provider=data.get("image", {}).get("provider", "")),
            tts=ModelMapping(provider=data.get("tts", {}).get("provider", "")),
            stt=ModelMapping(provider=data.get("stt", {}).get("provider", "")),
        )

    def _parse_bot(self, data: dict) -> BotConfig:
        """解析机器人行为配置"""
        bot_data = data.get("bot", {})
        context_data = data.get("context", {})
        selfie_data = data.get("selfie", {})
        wake_data = data.get("wake", {})

        bot_behavior = BotBehaviorConfig(
            max_memory_length=bot_data.get("max_memory_length", 10),
            max_message_interval=bot_data.get("max_message_interval", 2),
            max_buffer_messages=bot_data.get("max_buffer_messages", 5),
            min_message_delay=bot_data.get("min_message_delay", 0.8),
            max_message_delay=bot_data.get("max_message_delay", 1.5),
            typing_speed=bot_data.get("typing_speed", 50.0),
            typing_min_delay=bot_data.get("typing_min_delay", 0.5),
        )

        context = ContextConfig(
            max_context=context_data.get("max_context", 10),
            memory_enabled=context_data.get("memory_enabled", True),
            personality_strength=context_data.get("personality_strength", 0.8),
        )

        selfie = SelfieConfig(
            path=selfie_data.get("path", ""),
        )

        wake = WakeConfig(
            enable_keyword_wake=wake_data.get("enable_keyword_wake", False),
            waking_keywords=wake_data.get("waking_keywords", []),
            enable_quote_wake=wake_data.get("enable_quote_wake", False),
        )

        return BotConfig(bot=bot_behavior, context=context, selfie=selfie, wake=wake)

    def _parse_adapters(self, data: dict) -> AdaptersConfig:
        """解析适配器配置，通过 adapter_type 字段匹配各平台条目"""
        qq_data = {}
        tg_data = {}
        bili_data = {}

        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            adapter_type = str(value.get("adapter_type", key)).lower()
            if adapter_type == "qq" and not qq_data:
                qq_data = value
            elif adapter_type == "telegram" and not tg_data:
                tg_data = value
            elif adapter_type == "bilibili" and not bili_data:
                bili_data = value

        qq_config = AdapterConfig(
            enabled=qq_data.get("enabled", False),
            platform="QQ",
            desc=qq_data.get("desc", ""),
            bot_pid=str(qq_data.get("bot_pid", "")),
            owner_pid=str(qq_data.get("owner_pid", "")),
            ws_uri=qq_data.get("ws_url") or qq_data.get("ws_uri", ""),
            ws_listen_ip=qq_data.get("ws_listen_ip", ""),
            ws_token=qq_data.get("access_token") or qq_data.get("ws_token", ""),
            permission_mode=qq_data.get("permission_mode", "allow_list"),
            group_allow_list=qq_data.get("group_allow_list", []),
            user_allow_list=qq_data.get("user_allow_list", []),
            group_deny_list=qq_data.get("group_deny_list", []),
            user_deny_list=qq_data.get("user_deny_list", []),
            waking_keywords=qq_data.get("waking_keywords", []),
        )

        tg_config = AdapterConfig(
            enabled=tg_data.get("enabled", False),
            platform="Telegram",
            desc=tg_data.get("desc", ""),
            bot_pid=tg_data.get("bot_pid", ""),
            bot_token=tg_data.get("bot_token", ""),
            permission_mode=tg_data.get("permission_mode", "allow_list"),
            group_allow_list=tg_data.get("group_allow_list", []),
            user_allow_list=tg_data.get("user_allow_list", []),
            group_deny_list=tg_data.get("group_deny_list", []),
            user_deny_list=tg_data.get("user_deny_list", []),
        )

        bili_config = AdapterConfig(
            enabled=bili_data.get("enabled", False),
            platform="BiliBili",
            desc=bili_data.get("desc", ""),
            bot_uid=str(bili_data.get("bot_uid", "")),
            listening_bvid=bili_data.get("listening_bvid", ""),
            listening_interval=bili_data.get("listening_interval", 20),
            message_process_interval=bili_data.get("message_process_interval", 5),
            sessdata=bili_data.get("sessdata", ""),
            bili_jct=bili_data.get("bili_jct", ""),
            buvid3=bili_data.get("buvid3", ""),
            dedeuserid=bili_data.get("dedeuserid", ""),
            ac_time_value=bili_data.get("ac_time_value", ""),
        )

        return AdaptersConfig(qq=qq_config, telegram=tg_config, bilibili=bili_config)

    # ============ 属性 ============

    @property
    def config(self) -> ProvideConfig:
        return self._config

    def reload(self):
        """重新加载配置，成功后通知各组件"""
        self._load_all_configs()
        try:
            from ..bus import bus
            bus.emit("config_reloaded")
        except ImportError:
            pass

    # ============ 快捷访问 ============

    @property
    def persona(self) -> PersonaConfig:
        return self._config.persona

    @property
    def character(self) -> CharacterConfig:
        return self._config.persona.character

    @property
    def providers(self) -> Dict[str, ProviderConfig]:
        return self._config.providers

    @property
    def models(self) -> ModelsConfig:
        return self._config.models

    @property
    def bot(self) -> BotConfig:
        return self._config.bot

    @property
    def adapters(self) -> AdaptersConfig:
        return self._config.adapters

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        return self._config.providers.get(name)

    def get_active_provider(self, model_type: str) -> Optional[ProviderConfig]:
        model_mapping = getattr(self._config.models, model_type, None)
        if model_mapping and model_mapping.provider:
            provider = self._config.providers.get(model_mapping.provider)
            if provider:
                return provider
        # routing 未配置或 provider 名不匹配 → 回退到第一个可用 provider
        providers = self._config.providers
        if providers:
            return list(providers.values())[0]
        return None

    def get_api_config(self, model_type: str = "main_llm") -> Dict[str, str]:
        provider = self.get_active_provider(model_type)
        if provider:
            return {
                "api_key": provider.api_key,
                "model": provider.model,
                "url": provider.base_url,
            }
        return {"api_key": "", "model": "", "url": ""}

    @property
    def chat_api(self) -> Dict[str, str]:
        return self.get_api_config("main_llm")

    @property
    def plan_api(self) -> Dict[str, str]:
        return self.get_api_config("plan_llm")

    @property
    def tool_api(self) -> Dict[str, str]:
        return self.get_api_config("tool_llm")

    @property
    def max_context(self) -> int:
        return self._config.bot.context.max_context


# 全局单例
config_loader = ConfigLoader()
provide_config = config_loader
