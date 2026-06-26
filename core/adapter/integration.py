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

        # 监听配置热重载事件
        try:
            self.event_bus.on("config_reloaded", self._sync_adapter_configs)
        except Exception as e:
            logger.info("[AdapterBridge] 注册 config_reloaded 监听失败: %s", e)

        return self.manager

    def _load_adapter_configs(self):
        """从 platforms.yaml 直接加载适配器配置并加入待启动队列

        遍历 platforms.yaml 中所有条目，按 adapter_type 分类，
        使用实际条目名作为实例名，保留原始字段名传给适配器。
        """
        if not self.config_loader:
            return

        platforms_data = self.config_loader._load_yaml("config/platforms.yaml")

        for instance_name, config in platforms_data.items():
            if not isinstance(config, dict):
                continue
            if not config.get("enabled", False):
                continue

            adapter_type = str(config.get("adapter_type", "")).lower()
            if adapter_type not in ("qq", "telegram", "bilibili"):
                continue

            # 去除元数据字段，保留适配器自身需要的配置
            config_dict = {
                k: v for k, v in config.items()
                if k not in ("enabled", "adapter_type")
            }

            pending = getattr(self, '_pending_configs', [])
            pending.append((instance_name, config_dict, adapter_type))
            self._pending_configs = pending
            logger.info(
                "[AdapterBridge] %s adapter config loaded (instance=%s)",
                adapter_type, instance_name,
            )

    async def start_pending_adapters(self):
        """启动所有待启动的适配器

        应在事件循环运行后调用此方法。
        """
        pending = getattr(self, '_pending_configs', [])
        for item in pending:
            if len(item) == 3:
                adapter_id, config, adapter_type = item
            else:
                adapter_id, config = item
                adapter_type = None
            await self._start_adapter_async(adapter_id, config, adapter_type)
        self._pending_configs = []

    async def _start_adapter_async(self, adapter_id: str, config: Dict[str, Any], adapter_type: str = None):
        """异步启动适配器

        Args:
            adapter_id: 适配器实例名
            config: 适配器配置
            adapter_type: 适配器类型（如 qq, telegram）
        """
        try:
            success = await self.manager.start_adapter(adapter_id, config, adapter_type=adapter_type)
            if success:
                logger.info(f"[AdapterBridge] {adapter_id} adapter started successfully")
            else:
                logger.info(f"[AdapterBridge] Failed to start {adapter_id} adapter")
        except Exception as e:
            logger.info(f"[AdapterBridge] Error starting {adapter_id} adapter: {e}")

    def _sync_adapter_configs(self):
        """配置热重载后同步适配器状态（同步入口，派发异步任务）

        EventBus 使用同步 emit()，此处创建异步任务避免阻塞。
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._do_sync_adapter_configs())
        except RuntimeError:
            logger.info("[AdapterBridge] 无运行中的事件循环，跳过适配器同步")

    async def _do_sync_adapter_configs(self):
        """异步执行适配器配置同步

        对比当前运行中的适配器与最新配置，自动重启变更的适配器、
        启动新增的适配器、停止已删除的适配器。
        """
        if not self.manager or not self.config_loader:
            return

        try:
            platforms_data = self.config_loader._load_yaml("config/platforms.yaml")
        except Exception as e:
            logger.info("[AdapterBridge] 读取 platforms.yaml 失败: %s", e)
            return

        # 构建最新配置映射：instance_name -> (config_dict, adapter_type)
        new_configs = {}
        for instance_name, cfg in platforms_data.items():
            if not isinstance(cfg, dict):
                continue
            enabled = cfg.get("enabled", False)
            if not enabled:
                continue
            adapter_type = str(cfg.get("adapter_type", "")).lower()
            if adapter_type not in ("qq", "telegram", "bilibili"):
                continue
            config_dict = {
                k: v for k, v in cfg.items()
                if k not in ("enabled", "adapter_type")
            }
            new_configs[instance_name] = (config_dict, adapter_type)

        running = set(self.manager.list_running_adapters())
        configured = set(new_configs.keys())

        # 停止已删除的适配器
        for instance_name in running - configured:
            logger.info("[AdapterBridge] 适配器配置已删除，停止: %s", instance_name)
            await self.manager.stop_adapter(instance_name)

        # 启动新增的适配器
        for instance_name in configured - running:
            config_dict, adapter_type = new_configs[instance_name]
            logger.info("[AdapterBridge] 检测到新适配器，启动: %s", instance_name)
            await self._start_adapter_async(instance_name, config_dict, adapter_type)

        # 重启配置变更的适配器
        for instance_name in running & configured:
            old_adapter = self.manager.get_adapter(instance_name)
            if old_adapter is None:
                continue
            new_config_dict, adapter_type = new_configs[instance_name]
            # 比较配置是否变更（深度比较）
            if old_adapter.config != new_config_dict:
                logger.info("[AdapterBridge] 检测到配置变更，重启适配器: %s", instance_name)
                await self.manager.restart_adapter(instance_name, new_config_dict, adapter_type)

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
        images: Optional[list] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """广播消息到多个适配器

        Args:
            target_adapters: 目标适配器列表，None表示所有
            target_id: 目标ID
            text: 文本内容
            images: 图片路径列表
            **kwargs: 其他参数

        Returns:
            各适配器发送结果
        """
        if not self.manager:
            logger.info("[AdapterBridge] Manager not initialized")
            return {}

        return await self.manager.broadcast(target_adapters, target_id, text, images=images, **kwargs)

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

    Raises:
        RuntimeError: 桥接器未初始化且未提供必要参数
    """
    global _bridge_instance
    if _bridge_instance is None:
        if event_bus is None or config_loader is None:
            raise RuntimeError(
                "Bridge not initialized. Call get_bridge(event_bus, config_loader) first."
            )
        _bridge_instance = AdapterEventBridge(event_bus, config_loader)
    return _bridge_instance


def reset_bridge():
    """重置全局桥接器实例（用于测试）"""
    global _bridge_instance
    _bridge_instance = None
