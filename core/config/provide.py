import yaml
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


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
    # 其他可选参数
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelMapping:
    """模型映射配置类"""
    provider: str = ""


@dataclass
class ModelsConfig:
    """模型选择配置类"""
    main_llm: ModelMapping = field(default_factory=lambda: ModelMapping())
    tool_llm: ModelMapping = field(default_factory=lambda: ModelMapping())
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
class BotConfig:
    """完整的机器人配置类"""
    bot: BotBehaviorConfig = field(default_factory=BotBehaviorConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    selfie: SelfieConfig = field(default_factory=SelfieConfig)


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


@dataclass
class ProvideConfig:
    """完整的 Provide 配置类（包含所有配置）"""
    # 角色人设
    persona: PersonaConfig = field(default_factory=PersonaConfig)
    # 服务提供商
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    # 模型选择
    models: ModelsConfig = field(default_factory=ModelsConfig)
    # 机器人行为
    bot: BotConfig = field(default_factory=BotConfig)
    # 适配器配置
    adapters: AdaptersConfig = field(default_factory=AdaptersConfig)


class ConfigLoader:
    """多文件配置加载器"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
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
        # 加载各个配置文件（全部在 config 目录下）
        character_data = self._load_yaml("config/character.yaml")
        services_data = self._load_yaml("config/services.yaml")
        routing_data = self._load_yaml("config/routing.yaml")
        behavior_data = self._load_yaml("config/behavior.yaml")
        platforms_data = self._load_yaml("config/platforms.yaml")
        
        # 解析角色人设配置
        persona = self._parse_persona(character_data)
        
        # 解析服务提供商配置
        providers = self._parse_providers(services_data)
        
        # 解析模型选择配置
        models = self._parse_models(routing_data)
        
        # 解析机器人行为配置
        bot = self._parse_bot(behavior_data)
        
        # 解析适配器配置
        adapters = self._parse_adapters(platforms_data)

        # 加载插件配置
        plugins_data = self._load_yaml("config/plugins.yaml")
        self._plugins_config = plugins_data.get("plugins", {})

        # 组装完整配置
        self._config = ProvideConfig(
            persona=persona,
            providers=providers,
            models=models,
            bot=bot,
            adapters=adapters
        )
    
    def _parse_persona(self, data: dict) -> PersonaConfig:
        """解析角色人设配置"""
        char_data = data.get("character", {})
        
        # 处理 views 字段（可能是字符串或列表）
        views_data = char_data.get("views", "")
        if isinstance(views_data, list):
            views_str = "\n".join([str(v) for v in views_data if v])
        else:
            views_str = str(views_data) if views_data else ""
        
        # 处理 expressions 字段（可能是字典或列表）
        expressions_data = char_data.get("expressions", {})
        if isinstance(expressions_data, list):
            # 将列表转换为字典（使用索引作为键）
            expressions_dict = {f"expression_{i}": str(v) for i, v in enumerate(expressions_data) if v}
        elif isinstance(expressions_data, dict):
            expressions_dict = expressions_data
        else:
            expressions_dict = {}
        
        # 处理 dialogue_style_imitation 字段（可能是字符串列表或字典列表）
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
            dialogue_style_imitation=dialogue_list
        )
        
        return PersonaConfig(
            character=character,
            additional_prompt=data.get("additional_prompt", ""),
            additional_examples=data.get("additional_examples", [])
        )
    
    def _parse_providers(self, data: dict) -> Dict[str, ProviderConfig]:
        """解析服务提供商配置"""
        providers = {}
        
        for name, config in data.items():
            if isinstance(config, dict):
                # 提取已知字段
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
                    extra=extra
                )
        
        return providers
    
    def _parse_models(self, data: dict) -> ModelsConfig:
        """解析模型选择配置"""
        return ModelsConfig(
            main_llm=ModelMapping(provider=data.get("main_llm", {}).get("provider", "")),
            tool_llm=ModelMapping(provider=data.get("tool_llm", {}).get("provider", "")),
            vlm=ModelMapping(provider=data.get("vlm", {}).get("provider", "")),
            util_model=ModelMapping(provider=data.get("util_model", {}).get("provider", "")),
            image=ModelMapping(provider=data.get("image", {}).get("provider", "")),
            tts=ModelMapping(provider=data.get("tts", {}).get("provider", "")),
            stt=ModelMapping(provider=data.get("stt", {}).get("provider", ""))
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
            max_message_delay=bot_data.get("max_message_delay", 1.5)
        )
        
        context = ContextConfig(
            max_context=context_data.get("max_context", 10),
            memory_enabled=context_data.get("memory_enabled", True),
            personality_strength=context_data.get("personality_strength", 0.8)
        )
        
        selfie = SelfieConfig(
            path=selfie_data.get("path", "")
        )
        
        return BotConfig(
            bot=bot_behavior,
            context=context,
            selfie=selfie
        )
    
    def _parse_adapters(self, data: dict) -> AdaptersConfig:
        """解析适配器配置"""
        qq_data = data.get("qq", {})
        tg_data = data.get("telegram", {})
        bili_data = data.get("bilibili", {})
        
        qq_config = AdapterConfig(
            enabled=qq_data.get("enabled", False),
            platform="QQ",
            desc=qq_data.get("desc", ""),
            bot_pid=str(qq_data.get("bot_pid", "")),
            owner_pid=str(qq_data.get("owner_pid", "")),
            ws_uri=qq_data.get("ws_uri", ""),
            ws_listen_ip=qq_data.get("ws_listen_ip", ""),
            ws_token=qq_data.get("ws_token", ""),
            permission_mode=qq_data.get("permission_mode", "allow_list"),
            group_allow_list=qq_data.get("group_allow_list", []),
            user_allow_list=qq_data.get("user_allow_list", []),
            group_deny_list=qq_data.get("group_deny_list", []),
            user_deny_list=qq_data.get("user_deny_list", []),
            waking_keywords=qq_data.get("waking_keywords", [])
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
            user_deny_list=tg_data.get("user_deny_list", [])
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
            ac_time_value=bili_data.get("ac_time_value", "")
        )
        
        return AdaptersConfig(
            qq=qq_config,
            telegram=tg_config,
            bilibili=bili_config
        )
    
    @property
    def config(self) -> ProvideConfig:
        """获取配置对象"""
        return self._config
    
    def reload(self):
        """重新加载配置"""
        self._load_all_configs()
    
    # ============ 快捷访问方法 ============
    
    @property
    def persona(self) -> PersonaConfig:
        """获取角色人设配置"""
        return self._config.persona
    
    @property
    def character(self) -> CharacterConfig:
        """获取角色配置（兼容旧代码）"""
        return self._config.persona.character
    
    @property
    def providers(self) -> Dict[str, ProviderConfig]:
        """获取服务提供商配置"""
        return self._config.providers
    
    @property
    def models(self) -> ModelsConfig:
        """获取模型选择配置"""
        return self._config.models
    
    @property
    def bot(self) -> BotConfig:
        """获取机器人行为配置"""
        return self._config.bot
    
    @property
    def adapters(self) -> AdaptersConfig:
        """获取适配器配置"""
        return self._config.adapters
    
    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """获取指定名称的服务提供商配置"""
        return self._config.providers.get(name)
    
    def get_active_provider(self, model_type: str) -> Optional[ProviderConfig]:
        """获取当前激活的提供商配置（根据 routing.yaml 的映射）"""
        model_mapping = getattr(self._config.models, model_type, None)
        if model_mapping and model_mapping.provider:
            return self._config.providers.get(model_mapping.provider)
        return None
    
    def get_api_config(self, model_type: str = "main_llm") -> Dict[str, str]:
        """获取 API 配置（兼容旧代码）"""
        provider = self.get_active_provider(model_type)
        if provider:
            return {
                "api_key": provider.api_key,
                "model": provider.model,
                "url": provider.base_url
            }
        return {"api_key": "", "model": "", "url": ""}
    
    @property
    def chat_api(self) -> Dict[str, str]:
        """获取聊天 API 配置（兼容旧代码）"""
        return self.get_api_config("main_llm")
    
    @property
    def plan_api(self) -> Dict[str, str]:
        """获取计划 API 配置（兼容旧代码）"""
        return self.get_api_config("tool_llm")
    
    @property
    def tool_api(self) -> Dict[str, str]:
        """获取工具 API 配置（兼容旧代码）"""
        return self.get_api_config("tool_llm")
    
    @property
    def max_context(self) -> int:
        """获取最大上下文长度（兼容旧代码）"""
        return self._config.bot.context.max_context


# 全局配置实例（新）
config_loader = ConfigLoader()

# 兼容旧代码的全局配置实例
provide_config = config_loader


def get_character_prompt() -> str:
    """
    根据 character.yaml 生成角色提示词
    
    Returns:
        动态生成的角色提示词字符串
    """
    cfg = config_loader.persona
    char = cfg.character
    
    prompt_parts = []
    
    # 角色身份定义
    prompt_parts.append(f"你是 \"{char.ChineseName}\"（{char.EnglishName}），一个数字生命。")
    
    if char.NickNames:
        prompt_parts.append(f"用户也可以称呼你为：{', '.join(char.NickNames)}")
    
    prompt_parts.append("")
    
    # 基本信息
    prompt_parts.append("## 基本信息")
    prompt_parts.append(f"- 性别：{char.gender}")
    prompt_parts.append(f"- 年龄：{char.age}岁")
    if char.birthday:
        prompt_parts.append(f"- 生日：{char.birthday}")
    prompt_parts.append("")
    
    # 外貌描述
    if char.appearance:
        prompt_parts.append("## 外貌描述")
        prompt_parts.append(char.appearance)
        prompt_parts.append("")
    
    # 语言能力
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
    
    # 世界观
    if char.views:
        prompt_parts.append("## 世界观")
        prompt_parts.append(char.views)
        prompt_parts.append("")
    
    # 价值观
    if char.values:
        prompt_parts.append("## 价值观")
        for value in char.values:
            prompt_parts.append(f"- {value}")
        prompt_parts.append("")
    
    # 兴趣爱好
    if char.hobbies:
        prompt_parts.append("## 兴趣爱好")
        for hobby in char.hobbies:
            prompt_parts.append(f"- {hobby}")
        prompt_parts.append("")
    
    # 常用表达方式
    if char.expressions:
        prompt_parts.append("## 常用表达方式")
        for key, value in char.expressions.items():
            prompt_parts.append(f"- {key}：{value}")
        prompt_parts.append("")
    
    # 对话风格示例
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
                # 如果是字符串格式，直接显示
                prompt_parts.append(f"示例：{example}")
                prompt_parts.append("")
    
    # 额外提示词
    if cfg.additional_prompt:
        prompt_parts.append(cfg.additional_prompt)
        prompt_parts.append("")
    
    # 额外示例
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
    """
    获取对话示例列表
    
    Returns:
        对话示例列表，每个示例包含 user 和 assistant 字段
    """
    cfg = config_loader.persona
    examples = []
    
    # 从 dialogue_style_imitation 获取示例
    if cfg.character.dialogue_style_imitation:
        for item in cfg.character.dialogue_style_imitation:
            if isinstance(item, dict):
                examples.append(item)
            elif isinstance(item, str):
                # 尝试解析字符串格式
                examples.append({"user": item, "assistant": ""})
    
    # 从 additional_examples 获取示例
    if cfg.additional_examples:
        for example in cfg.additional_examples:
            if isinstance(example, dict):
                examples.append(example)
    
    return examples


# 便捷函数
def get_config() -> ProvideConfig:
    """获取完整配置对象"""
    return config_loader.config


def reload_config():
    """重新加载所有配置"""
    config_loader.reload()


# 兼容旧代码的全局配置变量
# 支持环境变量覆盖（优先级：环境变量 > YAML 配置 > 默认值）
CHAT_API_KEY = os.getenv("TALE_CHAT_API_KEY", config_loader.chat_api.get("api_key", ""))
CHAT_MODEL = os.getenv("TALE_CHAT_MODEL", config_loader.chat_api.get("model", ""))
CHAT_URL = os.getenv("TALE_CHAT_URL", config_loader.chat_api.get("url", ""))

PLAN_API_KEY = os.getenv("TALE_PLAN_API_KEY", config_loader.plan_api.get("api_key", ""))
PLAN_MODEL = os.getenv("TALE_PLAN_MODEL", config_loader.plan_api.get("model", ""))
PLAN_URL = os.getenv("TALE_PLAN_URL", config_loader.plan_api.get("url", ""))

TOOL_API_KEY = os.getenv("TALE_TOOL_API_KEY", config_loader.tool_api.get("api_key", ""))
TOOL_MODEL = os.getenv("TALE_TOOL_MODEL", config_loader.tool_api.get("model", ""))
TOOL_URL = os.getenv("TALE_TOOL_URL", config_loader.tool_api.get("url", ""))
