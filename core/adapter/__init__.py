"""
Tale 适配器模块

提供统一的平台接入接口，支持QQ、微信、WebSocket等多种平台。
基于 KiraAI 适配器系统设计。

Example:
    from core.adapter import AdapterManager, BaseAdapter, PlatformEvent

    async def on_event(event: PlatformEvent):
        print(f"[{event.platform.value}] {event.sender.name}: {event.content.text}")

    manager = AdapterManager(event_callback=on_event)
    await manager.start_adapter("qq", {"ws_url": "ws://localhost:3001"})
"""

from .base import BaseAdapter
from .event import (
    PlatformType,
    PlatformEvent,
    EventType,
    MessageContent,
    SenderInfo,
)
from .manager import AdapterManager
from .integration import AdapterEventBridge, get_bridge
from .message_processor import (
    MessageProcessor,
    ProcessorConfig,
    ProcessedMessage,
    ResponseDecision,
    PlatformConfigBuilder,
)

__all__ = [
    # 基类
    "BaseAdapter",
    # 事件相关
    "PlatformType",
    "PlatformEvent",
    "EventType",
    "MessageContent",
    "SenderInfo",
    # 管理器
    "AdapterManager",
    # 集成
    "AdapterEventBridge",
    "get_bridge",
    # 消息处理
    "MessageProcessor",
    "ProcessorConfig",
    "ProcessedMessage",
    "ResponseDecision",
    "PlatformConfigBuilder",
]
