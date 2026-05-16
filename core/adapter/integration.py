"""
适配器与事件总线集成模块

负责将适配器事件转换为内部事件总线事件，并处理消息流转。
"""

import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable

from .event import PlatformEvent, EventType, MessageContent
from .manager import AdapterManager
from ..utils import get_logger

logger = get_logger(__name__)


class AdapterEventBridge:
    """适配器事件桥接器

    将适配器的 PlatformEvent 转换为内部事件总线事件，
    并处理消息的发送和接收。
    """

    def __init__(self, event_bus, config_loader=None):
        """初始化桥接器

        Args:
            event_bus: 内部事件总线实例
            config_loader: 配置加载器实例
        """
        self.event_bus = event_bus
        self.config_loader = config_loader
        self.manager: Optional[AdapterManager] = None
        self._message_handlers: Dict[str, Callable] = {}

    async def _on_platform_event(self, event: PlatformEvent, adapter_id: str = None):
        """处理平台事件

        将 PlatformEvent 转换为内部事件并发布到事件总线。

        Args:
            event: 平台事件
            adapter_id: 来源适配器实例名
        """
        # 构建内部事件数据
        event_data = {
            "type": "platform_message",
            "platform": event.platform.value,
            "event_type": event.event_type.value,
            "adapter_instance": adapter_id,  # 记录来源适配器实例名
            "sender": {
                "id": event.sender.id,
                "name": event.sender.name,
                "avatar": event.sender.avatar,
                "is_bot": event.sender.is_bot,
            },
            "content": event.content.to_dict(),
            "message_id": event.message_id,
            "group_id": event.group_id,
            "group_name": event.group_name,
            "timestamp": event.timestamp.isoformat(),
            "raw_event": event.raw_event,
        }

        # 发布到事件总线
        self._emit_to_bus("platform_message", event_data)

        # 根据事件类型发布更具体的事件
        if event.event_type == EventType.PRIVATE_MESSAGE:
            self._emit_to_bus("private_message", event_data)
        elif event.event_type == EventType.GROUP_MESSAGE:
            self._emit_to_bus("group_message", event_data)

        # 发布平台特定事件
        self._emit_to_bus(f"{event.platform.value}_message", event_data)

    def _emit_to_bus(self, event_name: str, data: Dict[str, Any]):
        """安全地发布事件到事件总线

        Args:
            event_name: 事件名称
            data: 事件数据
        """
        try:
            # EventBus 有 aemit 方法（异步，支持协程回调）
            if hasattr(self.event_bus, 'aemit'):
                asyncio.create_task(self.event_bus.aemit(event_name, data))
            else:
                self.event_bus.emit(event_name, data)
        except Exception as e:
            logger.info(f"[AdapterBridge] Error emitting event {event_name}: {e}")

    def initialize(self):
        """初始化适配器管理器并加载配置"""
        # 创建适配器管理器，传入事件回调
        self.manager = AdapterManager(event_callback=self._on_platform_event)

        # 加载配置并启动适配器
        if self.config_loader:
            self._load_adapter_configs()

        return self.manager

    def _load_adapter_configs(self):
        """从配置加载器加载适配器配置并启动适配器"""
        if not self.config_loader:
            return

        adapters_config = self.config_loader.adapters

        # QQ 适配器
        if hasattr(adapters_config, 'qq') and adapters_config.qq.enabled:
            qq_config = adapters_config.qq
            
            # 处理 HTTP URL：从 ws_uri 推断，但使用标准端口
            ws_uri = qq_config.ws_uri or "ws://localhost:3001"
            if ":" in ws_uri.replace("://", ""):
                # 提取 host 和 port
                import re
                match = re.match(r'(ws|wss)://([^:]+):(\d+)', ws_uri)
                if match:
                    protocol, host, ws_port = match.groups()
                    http_protocol = "https" if protocol == "wss" else "http"
                    # NapCat HTTP API 通常使用 ws_port - 1 或 3000
                    http_port = int(ws_port) - 1 if int(ws_port) > 3000 else 3000
                    http_url = f"{http_protocol}://{host}:{http_port}"
                else:
                    http_url = ws_uri.replace("ws://", "http://").replace("wss://", "https://")
            else:
                http_url = ws_uri.replace("ws://", "http://").replace("wss://", "https://")
            
            config_dict = {
                "ws_url": ws_uri,
                "http_url": http_url,
                "access_token": qq_config.ws_token or "",
                "auto_reconnect": True,
                "reconnect_interval": 5,
                # 权限配置
                "permission_mode": qq_config.permission_mode,
                "group_allow_list": qq_config.group_allow_list,
                "user_allow_list": qq_config.user_allow_list,
                "group_deny_list": qq_config.group_deny_list,
                "user_deny_list": qq_config.user_deny_list,
                "waking_keywords": qq_config.waking_keywords,
                # 身份配置
                "bot_pid": qq_config.bot_pid,
                "owner_pid": qq_config.owner_pid,
            }
            # 保存配置，稍后异步启动
            self._pending_configs = getattr(self, '_pending_configs', [])
            self._pending_configs.append(("qq", config_dict))
            logger.info(f"[AdapterBridge] QQ adapter config loaded (will start when event loop is available)")

        # Telegram 适配器（待实现）
        if hasattr(adapters_config, 'telegram') and adapters_config.telegram.enabled:
            logger.info(f"[AdapterBridge] Telegram adapter not yet implemented")

        # BiliBili 适配器（待实现）
        if hasattr(adapters_config, 'bilibili') and adapters_config.bilibili.enabled:
            logger.info(f"[AdapterBridge] BiliBili adapter not yet implemented")

    async def start_pending_adapters(self):
        """启动所有待启动的适配器

        应在事件循环运行后调用此方法。
        """
        pending = getattr(self, '_pending_configs', [])
        for adapter_id, config in pending:
            await self._start_adapter_async(adapter_id, config)
        self._pending_configs = []

    async def _start_adapter_async(self, adapter_id: str, config: Dict[str, Any]):
        """异步启动适配器

        Args:
            adapter_id: 适配器ID
            config: 适配器配置
        """
        try:
            success = await self.manager.start_adapter(adapter_id, config)
            if success:
                logger.info(f"[AdapterBridge] {adapter_id} adapter started successfully")
            else:
                logger.info(f"[AdapterBridge] Failed to start {adapter_id} adapter")
        except Exception as e:
            logger.info(f"[AdapterBridge] Error starting {adapter_id} adapter: {e}")

    async def send_message(
        self,
        adapter_id: str,
        target_id: str,
        text: Optional[str] = None,
        images: Optional[list] = None,
        **kwargs
    ) -> bool:
        """通过指定适配器发送消息

        Args:
            adapter_id: 适配器ID
            target_id: 目标ID
            text: 文本内容
            images: 图片列表
            **kwargs: 其他参数

        Returns:
            发送是否成功
        """
        if not self.manager:
            logger.info("[AdapterBridge] Manager not initialized")
            return False

        return await self.manager.send_message(
            adapter_id, target_id, text, images, **kwargs
        )

    async def broadcast(
        self,
        target_adapters: Optional[list] = None,
        target_id: Optional[str] = None,
        text: Optional[str] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """广播消息到多个适配器

        Args:
            target_adapters: 目标适配器列表，None表示所有
            target_id: 目标ID
            text: 文本内容
            **kwargs: 其他参数

        Returns:
            各适配器发送结果
        """
        if not self.manager:
            logger.info("[AdapterBridge] Manager not initialized")
            return {}

        return await self.manager.broadcast(target_adapters, target_id, text, **kwargs)

    async def stop_all(self):
        """停止所有适配器"""
        if self.manager:
            await self.manager.stop_all()
            logger.info("[AdapterBridge] All adapters stopped")

    def get_manager(self) -> Optional[AdapterManager]:
        """获取适配器管理器实例"""
        return self.manager


# 全局桥接器实例
_bridge_instance: Optional[AdapterEventBridge] = None


def get_bridge(event_bus=None, config_loader=None) -> AdapterEventBridge:
    """获取全局桥接器实例

    Args:
        event_bus: 事件总线实例
        config_loader: 配置加载器实例

    Returns:
        AdapterEventBridge 实例
    """
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = AdapterEventBridge(event_bus, config_loader)
    return _bridge_instance


def reset_bridge():
    """重置全局桥接器实例（用于测试）"""
    global _bridge_instance
    _bridge_instance = None
