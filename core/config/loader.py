"""
配置加载器
===========
多文件 YAML 配置加载器，单例模式。
"""

import os
import threading
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
    BotConfig,
    AdapterConfig,
    AdaptersConfig,
    PersonaConfig,
    ProvideConfig,
)


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
            return yaml.safe_load(f) or {}

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

        bot_behavior = BotBehaviorConfig(
            max_memory_length=bot_data.get("max_memory_length", 10),
            max_message_interval=bot_data.get("max_message_interval", 2),
            max_buffer_messages=bot_data.get("max_buffer_messages", 5),
            min_message_delay=bot_data.get("min_message_delay", 0.8),
            max_message_delay=bot_data.get("max_message_delay", 1.5),
        )

        context = ContextConfig(
            max_context=context_data.get("max_context", 10),
            memory_enabled=context_data.get("memory_enabled", True),
            personality_strength=context_data.get("personality_strength", 0.8),
        )

        selfie = SelfieConfig(
            path=selfie_data.get("path", ""),
        )

        return BotConfig(bot=bot_behavior, context=context, selfie=selfie)

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
            return self._config.providers.get(model_mapping.provider)
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
