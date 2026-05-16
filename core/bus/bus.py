import asyncio
import inspect
from ..utils import get_logger

logger = get_logger(__name__)


class EventBus:
    def __init__(self):
        self._listeners = {}

    def on(self, event_name, callback):
        """订阅事件（同步或异步回调均可）"""
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)
        return self

    def off(self, event_name, callback=None):
        """取消订阅事件"""
        if event_name not in self._listeners:
            return self

        if callback is None:
            del self._listeners[event_name]
        else:
            self._listeners[event_name] = [
                cb for cb in self._listeners[event_name] if cb != callback
            ]
        return self

    def emit(self, event_name, *args, **kwargs):
        """触发同步事件"""
        if event_name not in self._listeners:
            return

        for callback in self._listeners[event_name]:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error("Error in event handler for %s: %s", event_name, e)

    async def aemit(self, event_name, *args, **kwargs):
        """触发异步事件，自动识别回调是否为协程函数"""
        if event_name not in self._listeners:
            return

        for callback in self._listeners[event_name]:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error("Error in async event handler for %s: %s", event_name, e)

    def once(self, event_name, callback):
        """只订阅一次"""
        def wrapper(*args, **kwargs):
            self.off(event_name, wrapper)
            callback(*args, **kwargs)

        self.on(event_name, wrapper)
        return self

    def aonce(self, event_name, callback):
        """只订阅一次（支持异步回调）"""
        async def wrapper(*args, **kwargs):
            self.off(event_name, wrapper)
            if inspect.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)

        self.on(event_name, wrapper)
        return self


bus = EventBus()
