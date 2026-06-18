"""
消息处理器模块

负责处理从适配器接收到的消息，包括：
- 权限检查（白名单/黑名单）
- 唤醒词检测
- 消息格式转换
- 路由决策

设计原则：
- 与具体平台无关，只处理通用逻辑
- 可配置的权限和响应策略
- 清晰的输入输出接口
"""

from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from .event import PlatformEvent, EventType, PlatformType


class ResponseDecision(Enum):
    """响应决策枚举"""
    RESPOND = "respond"           # 响应消息
    IGNORE = "ignore"             # 忽略消息
    SILENT = "silent"             # 静默处理（记录但不响应）


@dataclass
class ProcessedMessage:
    """处理后的消息格式

    从 PlatformEvent 转换而来，包含处理后的信息和决策结果
    """
    # 基本信息
    platform: PlatformType
    event_type: EventType
    message_id: Optional[str]

    # 发送者信息
    sender_id: str
    sender_name: str
    is_bot: bool = False

    # 内容信息
    text: Optional[str] = None
    images: List[str] = field(default_factory=list)
    at_targets: List[str] = field(default_factory=list)
    reply_to: Optional[str] = None
    reply_text: Optional[str] = None
    faces: List[Dict[str, Any]] = field(default_factory=list)
    stickers: List[Dict[str, Any]] = field(default_factory=list)
    videos: List[Dict[str, Any]] = field(default_factory=list)
    voices: List[Dict[str, Any]] = field(default_factory=list)
    json_cards: List[Dict[str, Any]] = field(default_factory=list)

    # 群组信息（如果是群消息）
    group_id: Optional[str] = None
    group_name: Optional[str] = None

    # 处理结果
    decision: ResponseDecision = ResponseDecision.IGNORE
    reason: str = ""  # 决策原因

    # 原始事件（用于调试和扩展）
    raw_event: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_group_message(self) -> bool:
        """是否为群消息"""
        return self.group_id is not None

    @property
    def is_private_message(self) -> bool:
        """是否为私聊消息"""
        return self.group_id is None

    def is_at_target(self, target_id: str) -> bool:
        """是否@了指定目标"""
        return target_id in self.at_targets

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "platform": self.platform.value,
            "event_type": self.event_type.value,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "is_bot": self.is_bot,
            "text": self.text,
            "images": self.images,
            "at_targets": self.at_targets,
            "reply_to": self.reply_to,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "decision": self.decision.value,
            "reason": self.reason,
        }


@dataclass
class ProcessorConfig:
    """消息处理器配置"""
    # 权限模式: "allow_list" | "deny_list" | "none"
    permission_mode: str = "allow_list"

    # 白名单
    group_allow_list: List[str] = field(default_factory=list)
    user_allow_list: List[str] = field(default_factory=list)

    # 黑名单
    group_deny_list: List[str] = field(default_factory=list)
    user_deny_list: List[str] = field(default_factory=list)

    # 唤醒词（群消息中需要包含这些词才会响应）
    waking_keywords: List[str] = field(default_factory=list)

    # 机器人ID（用于检测@）
    bot_id: str = ""

    # 私聊是否总是响应
    private_always_respond: bool = True

    # 群聊是否需要@或唤醒词
    group_need_at_or_keyword: bool = True

    # 关键词唤醒开关
    enable_keyword_wake: bool = False

    # 引用唤醒开关
    enable_quote_wake: bool = False

    # 已发送消息缓存（用于引用唤醒）
    sent_message_cache: Optional[Any] = None


class MessageProcessor:
    """消息处理器

    将 PlatformEvent 转换为 ProcessedMessage，并进行权限检查和决策。

    Example:
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=["example_group_id"],
            bot_id="bot_qq_id"
        )
        processor = MessageProcessor(config)

        processed = processor.process(platform_event)
        if processed.decision == ResponseDecision.RESPOND:
            # 处理消息
            reply = generate_reply(processed.text)
            send_reply(reply)
    """

    def __init__(self, config: Optional[ProcessorConfig] = None):
        """初始化消息处理器

        Args:
            config: 处理器配置，如果为 None 则使用默认配置
        """
        self.config = config or ProcessorConfig()

    def process(self, event: PlatformEvent) -> ProcessedMessage:
        """处理平台事件

        Args:
            event: 平台事件

        Returns:
            处理后的消息，包含决策结果
        """
        # 1. 转换事件格式
        message = self._convert_event(event)

        # 2. 权限检查
        if not self._check_permission(message):
            message.decision = ResponseDecision.IGNORE
            message.reason = "permission_denied"
            return message

        # 3. 决策是否需要响应
        decision, reason = self._make_decision(message)
        message.decision = decision
        message.reason = reason

        return message

    def _convert_event(self, event: PlatformEvent) -> ProcessedMessage:
        """将 PlatformEvent 转换为 ProcessedMessage

        Args:
            event: 平台事件

        Returns:
            处理后的消息
        """
        return ProcessedMessage(
            platform=event.platform,
            event_type=event.event_type,
            message_id=event.message_id,
            sender_id=event.sender.id,
            sender_name=event.sender.name,
            is_bot=event.sender.is_bot,
            text=event.content.text,
            images=event.content.images,
            at_targets=event.content.at_targets,
            reply_to=event.content.reply_to,
            reply_text=event.content.reply_text,
            faces=event.content.faces,
            stickers=event.content.stickers,
            videos=event.content.videos,
            voices=event.content.voices,
            json_cards=event.content.json_cards,
            group_id=event.group_id,
            group_name=event.group_name,
            raw_event=event.raw_event,
        )

    def _check_permission(self, message: ProcessedMessage) -> bool:
        """检查权限

        Args:
            message: 处理后的消息

        Returns:
            是否有权限
        """
        mode = self.config.permission_mode

        if mode == "none":
            return True

        # 检查用户黑名单
        if message.sender_id in self.config.user_deny_list:
            return False

        # 检查群组黑名单
        if message.group_id and message.group_id in self.config.group_deny_list:
            return False

        if mode == "deny_list":
            # 黑名单模式：不在黑名单中即可
            return True

        if mode == "allow_list":
            # 白名单模式：需要在白名单中

            # 私聊：检查用户白名单
            if message.is_private_message:
                if not self.config.user_allow_list:
                    return True  # 白名单为空表示允许所有人
                return message.sender_id in self.config.user_allow_list

            # 群聊：检查群组白名单或用户白名单
            if message.group_id:
                if self.config.group_allow_list:
                    if message.group_id in self.config.group_allow_list:
                        return True
                if self.config.user_allow_list:
                    if message.sender_id in self.config.user_allow_list:
                        return True
                # 如果白名单都为空，允许所有人
                if not self.config.group_allow_list and not self.config.user_allow_list:
                    return True
                return False

        return True

    def _make_decision(self, message: ProcessedMessage) -> tuple:
        """决策是否需要响应

        Args:
            message: 处理后的消息

        Returns:
            (决策, 原因)
        """
        # 私聊消息
        if message.is_private_message:
            if self.config.private_always_respond:
                return ResponseDecision.RESPOND, "private_message"
            return ResponseDecision.IGNORE, "private_not_always_respond"

        # 群聊消息
        if message.is_group_message:
            if not self.config.group_need_at_or_keyword:
                return ResponseDecision.RESPOND, "group_no_requirement"

            # 检查是否@了机器人
            # 优先使用配置的 bot_id，若未配置则从原始事件中获取 self_id（OneBot 协议字段）作为动态回退
            at_bot_id = self.config.bot_id or str(message.raw_event.get("self_id", ""))
            if at_bot_id and message.is_at_target(at_bot_id):
                return ResponseDecision.RESPOND, "at_bot"

            # 检查是否包含唤醒词
            if self.config.enable_keyword_wake and message.text and self.config.waking_keywords:
                text_lower = message.text.lower()
                for keyword in self.config.waking_keywords:
                    if keyword.lower() in text_lower:
                        return ResponseDecision.RESPOND, "waking_keyword"

            # 检查引用唤醒
            if (
                self.config.enable_quote_wake
                and message.reply_to
                and self.config.sent_message_cache
                and self.config.sent_message_cache.contains(message.reply_to)
            ):
                return ResponseDecision.RESPOND, "quote_wake"

            return ResponseDecision.IGNORE, "no_at_or_keyword"

        return ResponseDecision.IGNORE, "unknown_message_type"

    def update_config(self, config: ProcessorConfig):
        """更新配置

        Args:
            config: 新的配置
        """
        self.config = config

    def get_config(self) -> ProcessorConfig:
        """获取当前配置

        Returns:
            当前配置
        """
        return self.config


# 平台特定的配置构建器
class PlatformConfigBuilder:
    """平台配置构建器

    从配置加载器构建特定平台的 ProcessorConfig
    """

    @staticmethod
    def from_qq_config(qq_config, global_waking_keywords=None, enable_keyword_wake=False, enable_quote_wake=False) -> ProcessorConfig:
        """从 QQ 配置构建处理器配置

        Args:
            qq_config: QQ 适配器配置
            global_waking_keywords: 全局唤醒关键词（与平台关键词合并）
            enable_keyword_wake: 是否启用关键词唤醒
            enable_quote_wake: 是否启用引用唤醒

        Returns:
            处理器配置
        """
        waking_keywords = qq_config.waking_keywords
        if isinstance(waking_keywords, str):
            waking_keywords = [kw.strip() for kw in waking_keywords.split(",") if kw.strip()]
        waking_keywords = waking_keywords or []

        # 合并全局 + 平台关键词（全局优先，去重）
        if global_waking_keywords:
            seen = set()
            merged = []
            for kw in global_waking_keywords:
                if kw not in seen:
                    merged.append(kw)
                    seen.add(kw)
            for kw in waking_keywords:
                if kw not in seen:
                    merged.append(kw)
                    seen.add(kw)
            waking_keywords = merged

        from .sent_message_cache import sent_message_cache

        return ProcessorConfig(
            permission_mode=qq_config.permission_mode or "allow_list",
            group_allow_list=qq_config.group_allow_list or [],
            user_allow_list=qq_config.user_allow_list or [],
            group_deny_list=qq_config.group_deny_list or [],
            user_deny_list=qq_config.user_deny_list or [],
            waking_keywords=waking_keywords,
            bot_id=str(qq_config.bot_pid) if qq_config.bot_pid else "",
            private_always_respond=True,
            group_need_at_or_keyword=True,
            enable_keyword_wake=enable_keyword_wake,
            enable_quote_wake=enable_quote_wake,
            sent_message_cache=sent_message_cache,
        )
