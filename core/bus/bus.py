import asyncio
import inspect
import itertools
import threading
from ..utils import get_logger

logger = get_logger(__name__)


class EventBus:
    def __init__(self):
        self._listeners = {}
        self._lock = threading.RLock()
        self._seq = itertools.count()

    def on(self, event_name, callback, priority: int = 0):
        """订阅事件（同步或异步回调均可）

        Args:
            event_name: 事件名
            callback: 回调函数
            priority: 优先级（越大越先触发，默认 0）
        """
        with self._lock:
            if event_name not in self._listeners:
                self._listeners[event_name] = []
            # 存储为 (priority, seq, callback) 并按优先级排序
            entry = (priority, next(self._seq), callback)
            self._listeners[event_name].append(entry)
            self._listeners[event_name].sort(key=lambda x: (-x[0], x[1]))
        return self

    def off(self, event_name, callback=None):
        """取消订阅事件"""
        with self._lock:
            if event_name not in self._listeners:
                return self

            if callback is None:
                del self._listeners[event_name]
            else:
                self._listeners[event_name] = [
                    entry for entry in self._listeners[event_name]
                    if entry[2] != callback
                ]
        return self

    def emit(self, event_name, *args, **kwargs):
        """触发同步事件"""
        with self._lock:
            listeners = list(self._listeners.get(event_name, []))

        for _pri, _seq, callback in listeners:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error("Error in event handler for %s: %s", event_name, e)

    async def aemit(self, event_name, *args, **kwargs):
        """触发异步事件，自动识别回调是否为协程函数"""
        with self._lock:
            listeners = list(self._listeners.get(event_name, []))

        for _pri, _seq, callback in listeners:
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
