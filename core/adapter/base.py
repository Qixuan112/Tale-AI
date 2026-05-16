from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, Awaitable

from .event import PlatformType, PlatformEvent, MessageContent



from ..utils import get_logger

logger = get_logger(__name__)

class BaseAdapter(ABC):
    """适配器基类

    所有平台适配器必须继承此类并实现抽象方法。
    提供统一的消息收发接口和生命周期管理。

    Example:
        class QQAdapter(BaseAdapter):
            @property
            def platform(self) -> PlatformType:
                return PlatformType.QQ

            async def start(self):
                # 建立WebSocket连接
                pass

            async def stop(self):
                # 断开连接
                pass

            async def send_message(self, target_id: str, content: MessageContent) -> bool:
                # 发送消息
                pass

            def parse_event(self, raw_event: Dict) -> Optional[PlatformEvent]:
                # 解析事件
                pass
    """

    def __init__(
        self,
        config: Dict[str, Any],
        event_callback: Optional[Callable[[PlatformEvent], Awaitable[None]]] = None
    ):
        """初始化适配器

        Args:
            config: 适配器配置字典
            event_callback: 事件回调函数，当收到平台事件时调用
        """
        self.config = config
        self.event_callback = event_callback
        self._running = False
        self._adapter_id: Optional[str] = None

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """返回平台类型

        Returns:
            PlatformType: 平台类型枚举值
        """
        pass

    @property
    def is_running(self) -> bool:
        """适配器是否正在运行"""
        return self._running

    @property
    def adapter_id(self) -> Optional[str]:
        """适配器ID"""
        return self._adapter_id

    @adapter_id.setter
    def adapter_id(self, value: str):
        """设置适配器ID"""
        self._adapter_id = value

    @abstractmethod
    async def start(self):
        """启动适配器

        建立与平台的连接，开始监听事件。
        启动成功后应设置 self._running = True

        Raises:
            Exception: 启动失败时抛出异常
        """
        pass

    @abstractmethod
    async def stop(self):
        """停止适配器

        断开与平台的连接，清理资源。
        停止后应设置 self._running = False
        """
        pass

    @abstractmethod
    async def send_message(self, target_id: str, content: MessageContent) -> bool:
        """发送消息到指定目标

        Args:
            target_id: 目标ID（用户ID或群ID）
            content: 消息内容

        Returns:
            bool: 发送是否成功
        """
        pass

    @abstractmethod
    def parse_event(self, raw_event: Dict[str, Any]) -> Optional[PlatformEvent]:
        """解析原始事件为统一格式

        将平台特定的原始事件数据转换为 PlatformEvent 对象。
        如果事件不是消息类型或解析失败，返回 None。

        Args:
            raw_event: 原始事件数据

        Returns:
            Optional[PlatformEvent]: 解析后的事件对象，失败返回 None
        """
        pass

    async def emit_event(self, event: PlatformEvent):
        """触发事件回调

        当适配器收到平台事件时，调用此方法通知上层。
        同时传入适配器实例名，以便上层知道事件来自哪个实例。

        Args:
            event: 平台事件对象
        """
        if self.event_callback:
            try:
                await self.event_callback(event, adapter_id=self._adapter_id)
            except Exception as e:
                self.on_error(f"Error in event callback: {e}")

    def on_error(self, error_msg: str):
        """错误处理回调

        子类可以重写此方法实现自定义错误处理。

        Args:
            error_msg: 错误信息
        """
        logger.info(f"[{self.platform.value}] Adapter error: {error_msg}")

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值或默认值
        """
        return self.config.get(key, default)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(platform={self.platform.value}, running={self._running})>"
