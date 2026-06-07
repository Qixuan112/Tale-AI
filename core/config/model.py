"""
配置数据模型
=============
所有配置文件的 dataclass 模型定义。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class CharacterConfig:
    """角色配置类"""
    ChineseName: str = ""
    NickNames: List[str] = field(default_factory=list)
    EnglishName: str = ""
    gender: str = ""
    age: int = 0
    birthday: str = ""
    appearance: str = ""
    language: Dict[str, Any] = field(default_factory=dict)
    views: str = ""
    values: List[str] = field(default_factory=list)
    hobbies: List[str] = field(default_factory=list)
    expressions: Dict[str, str] = field(default_factory=dict)
    dialogue_style_imitation: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ProviderConfig:
    """服务提供商配置类"""
    type: str = ""
    format: str = ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    voice_name: str = ""
    timeout: int = 30
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelMapping:
    """模型映射配置类"""
    provider: str = ""


@dataclass
class ModelsConfig:
    """模型选择配置类"""
    main_llm: ModelMapping = field(default_factory=lambda: ModelMapping())
    plan_llm: ModelMapping = field(default_factory=lambda: ModelMapping())
    tool_llm: ModelMapping = field(default_factory=lambda: ModelMapping())
    generic_llm: ModelMapping = field(default_factory=lambda: ModelMapping())
    vlm: ModelMapping = field(default_factory=lambda: ModelMapping())
    util_model: ModelMapping = field(default_factory=lambda: ModelMapping())
    image: ModelMapping = field(default_factory=lambda: ModelMapping())
    tts: ModelMapping = field(default_factory=lambda: ModelMapping())
    stt: ModelMapping = field(default_factory=lambda: ModelMapping())


@dataclass
class BotBehaviorConfig:
    """机器人行为配置类"""
    max_memory_length: int = 10
    max_message_interval: int = 2
    max_buffer_messages: int = 5
    min_message_delay: float = 0.8
    max_message_delay: float = 1.5
    typing_speed: float = 50.0    # ms per character, simulates typing
    typing_min_delay: float = 0.5  # minimum delay in seconds for short messages


@dataclass
class ContextConfig:
    """上下文配置类"""
    max_context: int = 10
    memory_enabled: bool = True
    personality_strength: float = 0.8


@dataclass
class SelfieConfig:
    """自拍/头像配置类"""
    path: str = ""


@dataclass
class WakeConfig:
    """唤醒配置类"""
    enable_keyword_wake: bool = False
    waking_keywords: List[str] = field(default_factory=list)
    enable_quote_wake: bool = False


@dataclass
class BotConfig:
    """完整的机器人配置类"""
    bot: BotBehaviorConfig = field(default_factory=BotBehaviorConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    selfie: SelfieConfig = field(default_factory=SelfieConfig)
    wake: WakeConfig = field(default_factory=WakeConfig)


@dataclass
class AdapterConfig:
    """适配器配置类"""
    enabled: bool = False
    platform: str = ""
    desc: str = ""
    # QQ 特有
    bot_pid: str = ""
    owner_pid: str = ""
    ws_uri: str = ""
    ws_listen_ip: str = ""
    ws_token: str = ""
    permission_mode: str = "allow_list"
    group_allow_list: List[str] = field(default_factory=list)
    user_allow_list: List[str] = field(default_factory=list)
    group_deny_list: List[str] = field(default_factory=list)
    user_deny_list: List[str] = field(default_factory=list)
    waking_keywords: List[str] = field(default_factory=list)
    # Telegram 特有
    bot_token: str = ""
    # BiliBili 特有
    bot_uid: str = ""
    listening_bvid: str = ""
    listening_interval: int = 20
    message_process_interval: int = 5
    sessdata: str = ""
    bili_jct: str = ""
    buvid3: str = ""
    dedeuserid: str = ""
    ac_time_value: str = ""


@dataclass
class AdaptersConfig:
    """适配器集合配置类"""
    qq: AdapterConfig = field(default_factory=lambda: AdapterConfig(platform="QQ"))
    telegram: AdapterConfig = field(default_factory=lambda: AdapterConfig(platform="Telegram"))
    bilibili: AdapterConfig = field(default_factory=lambda: AdapterConfig(platform="BiliBili"))


@dataclass
class PersonaConfig:
    """角色人设配置类"""
    character: CharacterConfig = field(default_factory=CharacterConfig)
    additional_prompt: str = ""
    additional_examples: List[Dict[str, str]] = field(default_factory=list)
    raw_persona: str = ""  # 自由格式人格描述，优先于结构化字段


@dataclass
class ProvideConfig:
    """完整的 Provide 配置类（包含所有配置）"""
    persona: PersonaConfig = field(default_factory=PersonaConfig)
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    adapters: AdaptersConfig = field(default_factory=AdaptersConfig)
