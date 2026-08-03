# 适配器开发指南

## 概述

适配器（Adapter）是 Tale-AI 连接外部平台的桥梁，负责：
- 接收平台消息并转换为统一的 `PlatformEvent` 格式
- 将 Tale-AI 的回复发送到平台
- 管理连接生命周期（启动/停止/重连）

Tale-AI 采用**适配器模式**实现多平台支持，所有适配器继承 `BaseAdapter` 并实现统一接口。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        Tale-AI Core                          │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ PlatformEvent
                            │
┌───────────────────────────┼───────────────────────────┐
│                  AdapterEventBridge                    │
│           (统一事件桥接 → EventBus)                     │
└────────────────────────────────────────────────────────┘
                            ▲
                            │
            ┌───────────────┼───────────────┐
            │               │               │
        ┌───▼────┐     ┌───▼────┐     ┌───▼────┐
        │   QQ   │     │ WeChat │     │  WebSocket │
        │Adapter │     │Adapter │     │  Adapter   │
        └────────┘     └────────┘     └────────────┘
            │               │               │
        ┌───▼────┐     ┌───▼────┐     ┌───▼────┐
        │NapCat  │     │Windows │     │   WS   │
        │OneBot  │     │  UIA   │     │ Client │
        └────────┘     └────────┘     └────────┘
```

## 核心接口

### BaseAdapter

所有适配器必须继承 `BaseAdapter` 并实现以下抽象方法：

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from core.adapter.base import BaseAdapter
from core.adapter.event import (
    PlatformType, PlatformEvent, MessageContent, SendResult
)

class MyAdapter(BaseAdapter):
    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """返回平台类型"""
        pass
    
    @abstractmethod
    async def start(self):
        """启动适配器，建立连接"""
        pass
    
    @abstractmethod
    async def stop(self):
        """停止适配器，清理资源"""
        pass
    
    @abstractmethod
    async def send_message(
        self, target_id: str, content: MessageContent, **kwargs
    ) -> SendResult:
        """发送消息到指定目标"""
        pass
    
    @abstractmethod
    async def parse_event(
        self, raw_event: Dict[str, Any]
    ) -> Optional[PlatformEvent]:
        """解析原始事件为统一格式"""
        pass
```

### 核心数据结构

#### PlatformEvent

统一的平台事件格式：

```python
from dataclasses import dataclass
from datetime import datetime
from core.adapter.event import PlatformType, EventType, SenderInfo, MessageContent

@dataclass
class PlatformEvent:
    platform: PlatformType          # 平台类型（QQ/WeChat 等）
    event_type: EventType           # 事件类型（消息/通知等）
    sender: SenderInfo              # 发送者信息
    content: MessageContent         # 消息内容
    raw_event: Dict[str, Any]       # 原始事件数据
    timestamp: datetime             # 事件时间戳
    message_id: Optional[str]       # 消息 ID
    group_id: Optional[str]         # 群组 ID（群消息）
    group_name: Optional[str]       # 群组名称
```

#### MessageContent

标准化的消息内容：

```python
@dataclass
class MessageContent:
    text: Optional[str] = None                 # 文本内容
    images: List[str] = []                     # 图片 URL 列表
    at_targets: List[str] = []                 # @目标 ID 列表
    reply_to: Optional[str] = None             # 回复的消息 ID
    reply_text: Optional[str] = None           # 被回复消息的文本
    faces: List[Dict[str, Any]] = []           # 表情列表
    stickers: List[Dict[str, Any]] = []        # 贴纸列表
    videos: List[Dict[str, Any]] = []          # 视频列表
    voices: List[Dict[str, Any]] = []          # 语音列表
    json_cards: List[Dict[str, Any]] = []      # JSON 卡片列表
    files: List[FileAttachment] = []           # 文件附件列表
```

#### SendResult

消息发送结果：

```python
@dataclass
class SendResult:
    success: bool                   # 是否成功
    failed_files: List[str] = []    # 发送失败的文件名列表
    
    def __bool__(self) -> bool:
        return self.success  # 支持 if result: 语法
```

## 从零实现适配器

### 1. 创建适配器目录

```bash
core/adapter/src/
└── my_platform/
    ├── __init__.py
    ├── adapter.py      # 适配器主类
    └── client.py       # 平台客户端（可选）
```

### 2. 定义平台类型

在 `core/adapter/event.py` 中添加新平台：

```python
class PlatformType(Enum):
    QQ = "qq"
    WECHAT = "wechat"
    MY_PLATFORM = "my_platform"  # 新增
```

### 3. 实现适配器类

**完整示例** (`core/adapter/src/my_platform/adapter.py`)：

```python
import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

from core.adapter.base import BaseAdapter
from core.adapter.event import (
    PlatformType, PlatformEvent, EventType,
    MessageContent, SenderInfo, SendResult
)
from core.utils import get_logger

logger = get_logger(__name__)


class MyPlatformAdapter(BaseAdapter):
    """我的平台适配器
    
    基于 WebSocket 协议实现。
    
    配置示例:
        {
            "ws_url": "ws://localhost:8080",
            "api_key": "your_api_key",
            "bot_id": "bot_123"
        }
    """
    
    @property
    def platform(self) -> PlatformType:
        return PlatformType.MY_PLATFORM
    
    async def start(self):
        """启动适配器"""
        # 1. 读取配置
        self.ws_url = self.get_config("ws_url", "ws://localhost:8080")
        self.api_key = self.get_config("api_key", "")
        self.bot_id = self.get_config("bot_id", "")
        
        # 2. 初始化状态
        self.websocket = None
        self._running = False
        
        # 3. 建立连接
        try:
            import websockets
            self.websocket = await websockets.connect(
                self.ws_url,
                extra_headers={"Authorization": f"Bearer {self.api_key}"}
            )
            self._running = True
            logger.info(f"[MyPlatform] 已连接到 {self.ws_url}")
            
            # 4. 启动消息接收循环
            self._receive_task = asyncio.create_task(self._receive_loop())
            
        except Exception as e:
            logger.error(f"[MyPlatform] 启动失败: {e}")
            raise
    
    async def stop(self):
        """停止适配器"""
        self._running = False
        
        # 取消接收任务
        if hasattr(self, "_receive_task") and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # 关闭 WebSocket
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        logger.info("[MyPlatform] 适配器已停止")
    
    async def _receive_loop(self):
        """消息接收循环"""
        try:
            while self._running and self.websocket:
                try:
                    raw_message = await self.websocket.recv()
                    raw_event = json.loads(raw_message)
                    
                    # 解析事件
                    event = await self.parse_event(raw_event)
                    if event:
                        # 触发事件回调
                        await self.emit_event(event)
                
                except json.JSONDecodeError as e:
                    logger.warning(f"[MyPlatform] JSON 解析失败: {e}")
                except Exception as e:
                    logger.error(f"[MyPlatform] 处理消息失败: {e}")
        
        except asyncio.CancelledError:
            logger.info("[MyPlatform] 接收循环已取消")
        except Exception as e:
            logger.error(f"[MyPlatform] 接收循环异常: {e}")
            self._running = False
    
    async def parse_event(self, raw_event: Dict[str, Any]) -> Optional[PlatformEvent]:
        """解析原始事件为统一格式"""
        event_type_raw = raw_event.get("type")
        
        # 只处理消息事件
        if event_type_raw != "message":
            return None
        
        # 提取字段
        message_id = raw_event.get("id", "")
        sender_id = raw_event.get("sender_id", "")
        sender_name = raw_event.get("sender_name", sender_id)
        text = raw_event.get("text", "")
        images = raw_event.get("images", [])
        is_group = raw_event.get("is_group", False)
        group_id = raw_event.get("group_id") if is_group else None
        
        # 判断是否是机器人自己的消息
        is_bot = (sender_id == self.bot_id)
        
        # 构建发送者信息
        sender = SenderInfo(
            id=sender_id,
            name=sender_name,
            avatar=raw_event.get("sender_avatar"),
            is_bot=is_bot
        )
        
        # 构建消息内容
        content = MessageContent(
            text=text,
            images=images,
            at_targets=raw_event.get("mentions", []),
            reply_to=raw_event.get("reply_to")
        )
        
        # 确定事件类型
        if is_group:
            event_type = EventType.GROUP_MESSAGE
        else:
            event_type = EventType.PRIVATE_MESSAGE
        
        # 返回统一事件
        return PlatformEvent(
            platform=PlatformType.MY_PLATFORM,
            event_type=event_type,
            sender=sender,
            content=content,
            raw_event=raw_event,
            timestamp=datetime.now(),
            message_id=message_id,
            group_id=group_id
        )
    
    async def send_message(
        self, target_id: str, content: MessageContent, **kwargs
    ) -> SendResult:
        """发送消息"""
        if not self.websocket:
            logger.warning("[MyPlatform] WebSocket 未连接")
            return SendResult(success=False)
        
        try:
            # 构建发送数据
            is_group = kwargs.get("is_group", False)
            
            payload = {
                "action": "send_message",
                "target_id": target_id,
                "is_group": is_group,
                "text": content.text or "",
                "images": content.images,
                "mentions": content.at_targets,
                "reply_to": content.reply_to
            }
            
            # 发送到 WebSocket
            await self.websocket.send(json.dumps(payload))
            logger.info(f"[MyPlatform] 消息已发送到 {target_id}")
            
            return SendResult(success=True)
        
        except Exception as e:
            logger.error(f"[MyPlatform] 发送消息失败: {e}")
            return SendResult(success=False)
```

### 4. 注册适配器

在 `core/adapter/manager.py` 中注册新适配器：

```python
from core.adapter.src.my_platform.adapter import MyPlatformAdapter

# 在 AdapterManager 的 _registry 中添加
_registry: Dict[str, Type[BaseAdapter]] = {
    "qq": QQAdapter,
    "wechat_pc": WeChatPCAdapter,
    "websocket": WebSocketAdapter,
    "my_platform": MyPlatformAdapter,  # 新增
}
```

### 5. 配置适配器

在 `data/config/platforms.yaml` 中添加配置：

```yaml
adapters:
  - type: my_platform
    enabled: true
    config:
      ws_url: "ws://localhost:8080"
      api_key: "your_api_key"
      bot_id: "bot_123"
```

## 高级特性

### 1. 消息去重

防止平台重复推送同一条消息：

```python
from collections import OrderedDict

class MyAdapter(BaseAdapter):
    async def start(self):
        # ... 其他初始化代码 ...
        self._seen_msg_ids: OrderedDict[str, None] = OrderedDict()
    
    async def _receive_loop(self):
        while self._running:
            raw_event = await self._receive_message()
            
            # 去重检查
            msg_id = raw_event.get("id")
            if msg_id in self._seen_msg_ids:
                logger.debug(f"[MyPlatform] 重复消息: {msg_id}")
                continue
            
            # 记录已处理的消息 ID
            self._seen_msg_ids[msg_id] = None
            
            # 限制缓存大小（LRU）
            if len(self._seen_msg_ids) > 1000:
                self._seen_msg_ids = OrderedDict(
                    list(self._seen_msg_ids.items())[-500:]
                )
            
            event = await self.parse_event(raw_event)
            if event:
                await self.emit_event(event)
```

### 2. 自动重连

网络断开时自动重新连接：

```python
class MyAdapter(BaseAdapter):
    async def start(self):
        self.auto_reconnect = self.get_config("auto_reconnect", True)
        self._reconnect_delay = 5  # 重连延迟（秒）
        await self._connect()
    
    async def _connect(self):
        """建立连接（支持重试）"""
        while self._running:
            try:
                self.websocket = await websockets.connect(self.ws_url)
                logger.info("[MyPlatform] 连接成功")
                self._receive_task = asyncio.create_task(self._receive_loop())
                break
            except Exception as e:
                logger.error(f"[MyPlatform] 连接失败: {e}")
                if not self.auto_reconnect:
                    raise
                logger.info(f"[MyPlatform] {self._reconnect_delay}秒后重试...")
                await asyncio.sleep(self._reconnect_delay)
    
    async def _receive_loop(self):
        try:
            while self._running and self.websocket:
                message = await self.websocket.recv()
                # ... 处理消息 ...
        except websockets.ConnectionClosed:
            logger.warning("[MyPlatform] 连接已断开")
            if self.auto_reconnect and self._running:
                logger.info("[MyPlatform] 尝试重新连接...")
                await self._connect()
```

### 3. 文件上传

处理图片、文件等附件：

```python
async def send_message(
    self, target_id: str, content: MessageContent, **kwargs
) -> SendResult:
    failed_files = []
    
    # 上传图片
    uploaded_images = []
    for img_path in content.images:
        try:
            # 本地文件需要先上传
            if img_path.startswith("/") or img_path.startswith("C:"):
                img_url = await self._upload_file(img_path)
                uploaded_images.append(img_url)
            else:
                uploaded_images.append(img_path)
        except Exception as e:
            logger.warning(f"[MyPlatform] 图片上传失败: {e}")
            failed_files.append(img_path)
    
    # 发送消息
    payload = {
        "target_id": target_id,
        "text": content.text,
        "images": uploaded_images
    }
    await self.websocket.send(json.dumps(payload))
    
    return SendResult(
        success=True,
        failed_files=failed_files
    )

async def _upload_file(self, file_path: str) -> str:
    """上传文件到平台，返回 URL"""
    import aiohttp
    import base64
    
    with open(file_path, "rb") as f:
        file_data = base64.b64encode(f.read()).decode()
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{self.api_url}/upload",
            json={"file": file_data},
            headers={"Authorization": f"Bearer {self.api_key}"}
        ) as resp:
            result = await resp.json()
            return result["url"]
```

### 4. 引用消息处理

获取被回复消息的原文：

```python
async def parse_event(self, raw_event: Dict[str, Any]) -> Optional[PlatformEvent]:
    # ... 基本解析 ...
    
    # 处理引用消息
    reply_to = raw_event.get("reply_to")
    if reply_to:
        try:
            # 调用平台 API 获取原始消息
            original_msg = await self._get_message(reply_to)
            if original_msg:
                content.reply_text = f"{original_msg['sender']}: {original_msg['text']}"
        except Exception as e:
            logger.warning(f"[MyPlatform] 获取引用消息失败: {e}")
    
    return PlatformEvent(...)

async def _get_message(self, message_id: str) -> Optional[Dict]:
    """通过 API 获取历史消息"""
    payload = {
        "action": "get_message",
        "message_id": message_id
    }
    await self.websocket.send(json.dumps(payload))
    
    # 等待响应（需要实现请求-响应映射）
    response = await self._wait_for_response(message_id)
    return response.get("data")
```

### 5. 多实例支持

允许同时运行多个适配器实例：

```python
# platforms.yaml
adapters:
  - type: my_platform
    enabled: true
    instance_name: "bot_1"
    config:
      bot_id: "bot_123"
      ws_url: "ws://localhost:8080"
  
  - type: my_platform
    enabled: true
    instance_name: "bot_2"
    config:
      bot_id: "bot_456"
      ws_url: "ws://localhost:8081"
```

适配器通过 `adapter_id` 区分实例：

```python
async def emit_event(self, event: PlatformEvent):
    """触发事件时传入 adapter_id"""
    if self.event_callback:
        await self.event_callback(event, adapter_id=self._adapter_id)
```

## 测试方法

### 1. 单元测试

```python
import pytest
import asyncio
from core.adapter.src.my_platform.adapter import MyPlatformAdapter
from core.adapter.event import PlatformEvent, MessageContent

@pytest.fixture
async def adapter():
    config = {
        "ws_url": "ws://localhost:8080",
        "api_key": "test_key",
        "bot_id": "bot_test"
    }
    adapter = MyPlatformAdapter(config)
    yield adapter
    await adapter.stop()

@pytest.mark.asyncio
async def test_parse_event(adapter):
    """测试事件解析"""
    raw_event = {
        "type": "message",
        "id": "msg_123",
        "sender_id": "user_456",
        "sender_name": "张三",
        "text": "你好",
        "is_group": False
    }
    
    event = await adapter.parse_event(raw_event)
    
    assert event is not None
    assert event.sender.id == "user_456"
    assert event.content.text == "你好"
    assert event.event_type == EventType.PRIVATE_MESSAGE

@pytest.mark.asyncio
async def test_send_message(adapter):
    """测试消息发送"""
    # 模拟 WebSocket 连接
    adapter.websocket = MockWebSocket()
    
    content = MessageContent(text="测试消息", images=["http://example.com/img.jpg"])
    result = await adapter.send_message("user_123", content)
    
    assert result.success is True
    assert len(adapter.websocket.sent_messages) == 1
```

### 2. 集成测试

```python
@pytest.mark.asyncio
async def test_full_flow():
    """测试完整消息流"""
    received_events = []
    
    async def event_callback(event, adapter_id):
        received_events.append(event)
    
    # 启动适配器
    adapter = MyPlatformAdapter(config, event_callback=event_callback)
    await adapter.start()
    
    # 模拟接收消息
    await asyncio.sleep(1)
    
    # 发送消息
    content = MessageContent(text="回复")
    await adapter.send_message("user_123", content)
    
    # 验证
    assert len(received_events) > 0
    
    await adapter.stop()
```

### 3. Mock WebSocket

```python
class MockWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.received_messages = []
    
    async def send(self, message):
        self.sent_messages.append(message)
    
    async def recv(self):
        if not self.received_messages:
            await asyncio.sleep(0.1)
            return '{"type": "ping"}'
        return self.received_messages.pop(0)
    
    async def close(self):
        pass
```

## 配置管理

### 配置校验

```python
class MyAdapter(BaseAdapter):
    async def start(self):
        # 必需配置校验
        required = ["ws_url", "api_key", "bot_id"]
        for key in required:
            if not self.get_config(key):
                raise ValueError(f"缺少必需配置: {key}")
        
        # 类型校验
        timeout = self.get_config("timeout", 30)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout 必须是正数")
        
        # 启动连接
        await self._connect()
```

### 配置热更新

```python
from core.bus.bus import bus

class MyAdapter(BaseAdapter):
    def __init__(self, config, event_callback=None):
        super().__init__(config, event_callback)
        bus.on("config_reloaded", self._on_config_reload)
    
    async def _on_config_reload(self):
        """配置重载时触发"""
        old_url = self.ws_url
        new_url = self.get_config("ws_url", "")
        
        if new_url != old_url:
            logger.info("[MyPlatform] 检测到 URL 变化，重新连接...")
            await self.stop()
            await self.start()
```

## 错误处理

### 优雅降级

```python
async def send_message(
    self, target_id: str, content: MessageContent, **kwargs
) -> SendResult:
    try:
        # 尝试发送
        await self._send_impl(target_id, content, **kwargs)
        return SendResult(success=True)
    
    except ConnectionError as e:
        logger.error(f"[MyPlatform] 连接错误: {e}")
        # 触发重连
        if self.auto_reconnect:
            asyncio.create_task(self._reconnect())
        return SendResult(success=False)
    
    except TimeoutError:
        logger.warning("[MyPlatform] 发送超时")
        return SendResult(success=False)
    
    except Exception as e:
        logger.error(f"[MyPlatform] 未知错误: {e}", exc_info=True)
        return SendResult(success=False)
```

### 重试机制

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def _send_with_retry(self, payload: dict):
    """带重试的发送"""
    if not self.websocket:
        raise ConnectionError("WebSocket 未连接")
    await self.websocket.send(json.dumps(payload))
```

## 最佳实践

### 1. 日志记录

```python
logger.info("[MyPlatform] 适配器已启动")
logger.debug(f"[MyPlatform] 收到原始事件: {raw_event}")
logger.warning(f"[MyPlatform] 连接不稳定，延迟: {latency}ms")
logger.error(f"[MyPlatform] 发送失败: {error}", exc_info=True)
```

### 2. 资源清理

```python
async def stop(self):
    # 1. 停止标志
    self._running = False
    
    # 2. 取消异步任务
    for task in [self._receive_task, self._heartbeat_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    # 3. 关闭连接
    if self.websocket:
        await self.websocket.close()
    
    # 4. 清理缓存
    self._seen_msg_ids.clear()
```

### 3. 性能优化

```python
# 批量发送
async def send_messages_batch(self, messages: List[tuple]):
    """批量发送消息"""
    tasks = [
        self.send_message(target, content, **kwargs)
        for target, content, kwargs in messages
    ]
    return await asyncio.gather(*tasks, return_exceptions=True)

# 消息队列
from asyncio import Queue

class MyAdapter(BaseAdapter):
    async def start(self):
        self._send_queue = Queue(maxsize=100)
        self._sender_task = asyncio.create_task(self._sender_loop())
    
    async def _sender_loop(self):
        """消息发送队列"""
        while self._running:
            try:
                target, content, kwargs = await self._send_queue.get()
                await self._send_impl(target, content, **kwargs)
            except Exception as e:
                logger.error(f"发送失败: {e}")
```

### 4. 安全性

```python
# URL 白名单
ALLOWED_DOMAINS = ["example.com", "cdn.example.com"]

def _validate_url(self, url: str) -> bool:
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    return any(domain.endswith(d) for d in ALLOWED_DOMAINS)

# 防止 SSRF
async def _upload_file(self, url: str):
    if not self._validate_url(url):
        raise ValueError(f"不允许的域名: {url}")
    # ... 上传逻辑 ...
```

## 常见问题

### Q: 适配器启动失败

**A**: 检查以下几点：
1. 配置是否正确（`platforms.yaml`）
2. 网络连接是否正常
3. 平台服务是否已启动
4. 日志中的具体错误信息

### Q: 消息接收不到

**A**: 
1. 确认 `_receive_loop` 正在运行
2. 检查 `parse_event` 是否正确返回 `PlatformEvent`
3. 确认 `emit_event` 被正确调用
4. 查看平台是否正确推送消息

### Q: 发送消息失败

**A**:
1. 检查 WebSocket 连接状态
2. 确认 `target_id` 格式正确
3. 查看平台 API 返回的错误码
4. 检查消息内容是否符合平台限制

### Q: 如何调试网络问题

**A**:
```python
import logging
logging.getLogger("websockets").setLevel(logging.DEBUG)
```

## 下一步

- [插件开发](plugin-development.md) — 开发自定义插件
- [贡献指南](contributing.md) — 向 Tale-AI 贡献代码
- [事件系统](../architecture/event-system.md) — 理解 EventBus
