from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime


class PlatformType(Enum):
    """平台类型枚举"""
    QQ = "qq"
    WECHAT = "wechat"
    WECHAT_PC = "wechat_pc"
    WECHAT_MOMENTS = "wechat_moments"
    WEBSOCKET = "websocket"
    CUSTOM = "custom"


class EventType(Enum):
    """事件类型枚举"""
    MESSAGE = "message"
    PRIVATE_MESSAGE = "private_message"
    GROUP_MESSAGE = "group_message"
    NOTICE = "notice"
    MOMENTS_POST = "moments_post"
    JOIN = "join"
    LEAVE = "leave"
    FRIEND_REQUEST = "friend_request"
    GROUP_INVITE = "group_invite"
    UNKNOWN = "unknown"


@dataclass
class MessageContent:
    """标准化消息内容"""
    text: Optional[str] = None
    images: List[str] = field(default_factory=list)
    at_targets: List[str] = field(default_factory=list)
    reply_to: Optional[str] = None
    reply_text: Optional[str] = None
    raw_content: Any = None
    faces: List[Dict[str, Any]] = field(default_factory=list)
    stickers: List[Dict[str, Any]] = field(default_factory=list)
    videos: List[Dict[str, Any]] = field(default_factory=list)
    voices: List[Dict[str, Any]] = field(default_factory=list)
    json_cards: List[Dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        """检查消息是否为空"""
        return not self.text and not self.images and not self.faces and not self.stickers and not self.videos and not self.voices and not self.json_cards

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "text": self.text,
            "images": self.images,
            "at_targets": self.at_targets,
            "reply_to": self.reply_to,
            "reply_text": self.reply_text,
            "faces": self.faces,
            "stickers": self.stickers,
            "videos": self.videos,
            "voices": self.voices,
            "json_cards": self.json_cards,
        }


@dataclass
class SenderInfo:
    """发送者信息"""
    id: str
    name: str
    avatar: Optional[str] = None
    is_bot: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformEvent:
    """统一平台事件格式

    所有平台适配器必须将原始事件转换为这个统一格式
    """
    platform: PlatformType
    event_type: EventType
    sender: SenderInfo
    content: MessageContent
    raw_event: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None

    def is_group_message(self) -> bool:
        """是否为群消息"""
        return self.event_type == EventType.GROUP_MESSAGE

    def is_private_message(self) -> bool:
        """是否为私聊消息"""
        return self.event_type == EventType.PRIVATE_MESSAGE

    def is_at_me(self, bot_id: str) -> bool:
        """是否@了机器人"""
        return bot_id in self.content.at_targets

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化"""
        return {
            "platform": self.platform.value,
            "event_type": self.event_type.value,
            "sender": {
                "id": self.sender.id,
                "name": self.sender.name,
                "avatar": self.sender.avatar,
                "is_bot": self.sender.is_bot,
            },
            "content": self.content.to_dict(),
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id,
            "group_id": self.group_id,
            "group_name": self.group_name,
        }
