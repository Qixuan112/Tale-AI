# 适配器架构

## 概述

Tale-AI 的适配器系统提供统一的**多平台接入能力**，将不同平台（QQ、微信、WebSocket 等）的消息转换为统一格式，实现"一次开发，多平台运行"。

## 设计目标

- **统一接口** — 所有平台适配器实现相同的抽象接口
- **热插拔** — 运行时启动/停止适配器，无需重启
- **自动发现** — 扫描 `core/adapter/src/` 目录自动注册
- **隔离错误** — 单个适配器失败不影响其他适配器
- **灵活路由** — 支持多实例，按平台类型或实例名路由

---

## 核心组件

### 架构图

```
┌─────────────────────────────────────────────────────┐
│                  平台层                              │
│  QQ (OneBot)  │  WeChat PC  │  WebSocket  │ ...    │
└────────┬─────────────┬────────────┬────────────────┘
         │             │            │
    ┌────▼─────────────▼────────────▼────┐
    │         BaseAdapter                 │  ← 抽象基类
    │  • parse_event()                   │
    │  • send_message()                  │
    │  • start() / stop()                │
    └────────────┬───────────────────────┘
                 │
    ┌────────────▼───────────────────────┐
    │      AdapterManager                │  ← 生命周期管理
    │  • 注册/扫描适配器                  │
    │  • 启动/停止适配器                  │
    │  • 消息路由                        │
    └────────────┬───────────────────────┘
                 │
    ┌────────────▼───────────────────────┐
    │    AdapterEventBridge              │  ← 事件桥接
    │  平台事件 → EventBus               │
    └────────────┬───────────────────────┘
                 │
    ┌────────────▼───────────────────────┐
    │         EventBus                    │  ← 事件总线
    │  emit("platform_message", event)   │
    └────────────────────────────────────┘
```

---

## BaseAdapter — 抽象基类

所有平台适配器必须继承 `BaseAdapter` 并实现抽象方法。

**文件位置**：[core/adapter/base.py](../../core/adapter/base.py)

### 抽象方法

```python
from abc import ABC, abstractmethod
from typing import Optional
from core.adapter.base import BaseAdapter
from core.adapter.event import PlatformType, PlatformEvent, MessageContent, SendResult

class MyAdapter(BaseAdapter):
    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """返回平台类型"""
        return PlatformType.CUSTOM
    
    @abstractmethod
    async def start(self):
        """启动适配器（建立连接）"""
        self._running = True
        # 连接逻辑...
    
    @abstractmethod
    async def stop(self):
        """停止适配器（断开连接）"""
        self._running = False
        # 清理逻辑...
    
    @abstractmethod
    async def send_message(self, target_id: str, content: MessageContent, **kwargs) -> SendResult:
        """发送消息"""
        # 发送逻辑...
        return SendResult(success=True)
    
    @abstractmethod
    async def parse_event(self, raw_event: dict) -> Optional[PlatformEvent]:
        """解析原始事件为统一格式"""
        # 解析逻辑...
        return PlatformEvent(...)
```

### 生命周期

```python
# 1. 初始化
adapter = MyAdapter(config, event_callback)

# 2. 启动
await adapter.start()
# - 建立连接
# - 设置 self._running = True
# - 开始监听事件

# 3. 运行中
# - 接收平台事件
# - 调用 await parse_event() 转换
# - 调用 await emit_event() 通知上层

# 4. 停止
await adapter.stop()
# - 断开连接
# - 设置 self._running = False
# - 清理资源
```

---

## PlatformEvent — 统一事件格式

所有平台的消息都转换为 `PlatformEvent`。

**文件位置**：[core/adapter/event.py](../../core/adapter/event.py)

### 数据结构

```python
from dataclasses import dataclass
from datetime import datetime
from core.adapter.event import PlatformType, EventType, MessageContent, SenderInfo

@dataclass
class PlatformEvent:
    platform: PlatformType          # 平台类型（qq/wechat/websocket）
    event_type: EventType           # 事件类型（message/group_message/notice）
    sender: SenderInfo              # 发送者信息
    content: MessageContent         # 消息内容
    raw_event: dict                 # 原始事件（用于调试）
    timestamp: datetime             # 时间戳
    message_id: Optional[str]       # 消息 ID
    group_id: Optional[str]         # 群 ID（群消息时）
    group_name: Optional[str]       # 群名称
```

### 枚举类型

#### PlatformType

```python
class PlatformType(Enum):
    QQ = "qq"
    WECHAT = "wechat"
    WECHAT_PC = "wechat_pc"
    WECHAT_MOMENTS = "wechat_moments"
    WEBSOCKET = "websocket"
    CUSTOM = "custom"
```

#### EventType

```python
class EventType(Enum):
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
```

### MessageContent

```python
@dataclass
class MessageContent:
    text: Optional[str] = None              # 文本内容
    images: List[str] = []                  # 图片 URL 列表
    at_targets: List[str] = []              # @的用户 ID 列表
    reply_to: Optional[str] = None          # 回复的消息 ID
    reply_text: Optional[str] = None        # 被回复的消息文本
    faces: List[Dict] = []                  # 表情
    stickers: List[Dict] = []               # 贴纸
    videos: List[Dict] = []                 # 视频
    voices: List[Dict] = []                 # 语音
    json_cards: List[Dict] = []             # JSON 卡片
    files: List[FileAttachment] = []        # 文件附件
```

### SenderInfo

```python
@dataclass
class SenderInfo:
    id: str                     # 用户 ID
    name: str                   # 用户昵称
    avatar: Optional[str]       # 头像 URL
    is_bot: bool = False        # 是否为机器人
    extra: Dict = {}            # 额外信息
```

---

## AdapterManager — 生命周期管理

管理所有适配器的注册、启动、停止和消息路由。

**文件位置**：[core/adapter/manager.py](../../core/adapter/manager.py)

### 初始化

```python
from core.adapter.manager import AdapterManager

async def on_event(event: PlatformEvent, adapter_id: str):
    print(f"[{adapter_id}] 收到消息: {event.content.text}")

manager = AdapterManager(
    config=global_config,
    event_callback=on_event
)
```

### 自动扫描

AdapterManager 启动时自动扫描 `core/adapter/src/` 目录：

```
core/adapter/src/
├── qq/
│   ├── manifest.json       # 适配器元数据
│   ├── schema.json         # 配置 Schema（可选）
│   └── adapter.py          # 适配器实现
├── wechat_pc/
│   ├── manifest.json
│   └── adapter.py
└── websocket/
    ├── manifest.json
    └── adapter.py
```

**manifest.json 示例**：
```json
{
  "id": "qq",
  "name": "QQ Adapter",
  "version": "1.0.0",
  "author": "Tale-AI Team",
  "description": "QQ 适配器（OneBot 11 协议）"
}
```

### 启动适配器

```python
# 启动单个适配器
await manager.start_adapter(
    adapter_id="qq_bot_1",        # 实例名（唯一标识）
    adapter_config={              # 适配器配置
        "ws_url": "ws://localhost:8080",
        "access_token": "your-token"
    },
    adapter_type="qq"             # 适配器类型（用于查找适配器类）
)
```

**参数说明**：
- `adapter_id` — 实例的唯一标识（用于消息路由）
- `adapter_type` — 适配器类型（从扫描结果中查找，默认与 `adapter_id` 相同）
- `adapter_config` — 传递给适配器的配置字典

### 停止适配器

```python
# 停止单个适配器
await manager.stop_adapter("qq_bot_1")

# 停止所有适配器
await manager.stop_all()
```

### 查询适配器

```python
# 列出所有可用的适配器类型
adapter_types = AdapterManager.list_adapters()
# 返回: ["qq", "wechat_pc", "websocket"]

# 获取适配器信息
info = AdapterManager.get_adapter_info("qq")
# 返回: {"id": "qq", "name": "QQ Adapter", "version": "1.0.0", ...}

# 列出正在运行的实例
running = manager.list_running_adapters()
# 返回: ["qq_bot_1", "qq_bot_2", "wechat_pc_1"]

# 获取运行中的适配器实例
adapter = manager.get_adapter("qq_bot_1")
```

---

## 消息路由

### 精确路由

通过实例名精确路由：

```python
# 发送消息到特定实例
result = await manager.send_message(
    adapter_id="qq_bot_1",        # 实例名
    target_id="user_12345",
    text="你好！"
)
```

### 自动路由

通过平台类型自动路由到该平台的第一个运行实例：

```python
# 发送消息到 QQ 平台（自动选择运行中的 QQ 实例）
result = await manager.send_message(
    adapter_id="qq",              # 平台类型
    target_id="user_12345",
    text="你好！"
)

# 内部解析流程：
# 1. "qq" 不是运行中的实例名
# 2. 查找平台索引：_platform_index["qq"] = ["qq_bot_1", "qq_bot_2"]
# 3. 选择第一个：qq_bot_1
# 4. 路由到 qq_bot_1
```

### 发送结果

```python
from core.adapter.event import SendResult

result = await manager.send_message(...)

if result.success:
    print("发送成功")
else:
    print(f"发送失败，未送达文件: {result.failed_files}")

# SendResult 支持 truthiness 检查
if result:
    print("成功")
```

### 广播消息

```python
# 广播到所有运行中的适配器
results = await manager.broadcast(
    text="系统通知：维护中",
    target_id="group_123"
)

# 返回: {"qq_bot_1": SendResult(...), "wechat_pc_1": SendResult(...)}

# 广播到指定适配器
results = await manager.broadcast(
    target_adapters=["qq_bot_1", "qq_bot_2"],
    text="群发消息",
    target_id="user_456"
)
```

---

## 平台适配器实现

### QQ 适配器（OneBot 11）

基于 NapCat/OneBot 11 协议的 WebSocket 连接。

**文件位置**：[core/adapter/src/qq/adapter.py](../../core/adapter/src/qq/adapter.py)

#### 配置示例

```yaml
# data/config/platforms.yaml
qq:
  - id: "qq_bot_1"
    enabled: true
    ws_url: "ws://localhost:8080"
    access_token: "your-token"
    reconnect: true
    reconnect_interval: 5
```

#### 事件转换

```python
# OneBot 原始事件
{
  "post_type": "message",
  "message_type": "group",
  "group_id": 123456,
  "user_id": 789,
  "message": "你好",
  "sender": {
    "nickname": "张三",
    "card": "管理员"
  }
}

# 转换为 PlatformEvent
PlatformEvent(
    platform=PlatformType.QQ,
    event_type=EventType.GROUP_MESSAGE,
    sender=SenderInfo(id="789", name="张三"),
    content=MessageContent(text="你好"),
    group_id="123456",
    group_name=None
)
```

#### 消息发送

```python
# 私聊
await manager.send_message(
    adapter_id="qq",
    target_id="user_789",
    text="你好！",
    is_group=False
)

# 群聊
await manager.send_message(
    adapter_id="qq",
    target_id="123456",
    text="大家好！",
    is_group=True
)

# @某人
await manager.send_message(
    adapter_id="qq",
    target_id="123456",
    text="请注意",
    is_group=True,
    at_targets=["789"]
)

# 发送图片
await manager.send_message(
    adapter_id="qq",
    target_id="123456",
    text="看这张图",
    images=["https://example.com/image.jpg"],
    is_group=True
)
```

### WeChat PC 适配器

基于 Windows UIAutomation 的桌面自动化。

**文件位置**：[core/adapter/src/wechat_pc/adapter.py](../../core/adapter/src/wechat_pc/adapter.py)

#### 配置示例

```yaml
# data/config/platforms.yaml
wechat_pc:
  - id: "wechat_pc_1"
    enabled: true
    poll_interval: 1.0        # 轮询间隔（秒）
    monitor_window: true      # 监控窗口状态
```

#### 特性

- **Windows 专用** — 仅支持 Windows 10/11
- **无需 Hook** — 使用官方 UIAutomation API
- **自动发现** — 自动查找微信窗口
- **轮询机制** — 定期检查新消息

#### 限制

- 需要微信客户端保持运行
- 无法获取历史消息
- 群聊支持有限

### WebSocket 适配器

通用 WebSocket 服务器/客户端适配器。

**文件位置**：[core/adapter/src/websocket/adapter.py](../../core/adapter/src/websocket/adapter.py)

#### 配置示例

```yaml
# data/config/platforms.yaml
websocket:
  - id: "ws_server"
    enabled: true
    mode: "server"            # server 或 client
    host: "0.0.0.0"
    port: 8765
  
  - id: "ws_client"
    enabled: true
    mode: "client"
    url: "ws://remote-server:8765"
```

#### 消息格式

```json
// 接收消息
{
  "type": "message",
  "sender_id": "user_123",
  "sender_name": "张三",
  "text": "你好",
  "timestamp": "2026-08-03T14:30:00"
}

// 发送消息
{
  "type": "reply",
  "target_id": "user_123",
  "text": "你好！"
}
```

---

## 开发自定义适配器

### 1. 创建目录结构

```bash
mkdir -p core/adapter/src/my_platform
cd core/adapter/src/my_platform
```

### 2. 编写 manifest.json

```json
{
  "id": "my_platform",
  "name": "My Platform Adapter",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "我的自定义平台适配器"
}
```

### 3. 实现适配器

```python
# core/adapter/src/my_platform/adapter.py
from typing import Optional
from core.adapter.base import BaseAdapter
from core.adapter.event import (
    PlatformType, PlatformEvent, EventType,
    MessageContent, SenderInfo, SendResult
)

class MyPlatformAdapter(BaseAdapter):
    @property
    def platform(self) -> PlatformType:
        return PlatformType.CUSTOM
    
    async def start(self):
        """建立连接"""
        self._running = True
        # 连接到平台 API...
        await self._connect()
    
    async def stop(self):
        """断开连接"""
        self._running = False
        await self._disconnect()
    
    async def send_message(self, target_id: str, content: MessageContent, **kwargs) -> SendResult:
        """发送消息"""
        try:
            # 调用平台 API 发送消息
            await self.platform_api.send(
                user_id=target_id,
                text=content.text
            )
            return SendResult(success=True)
        except Exception as e:
            self.on_error(f"发送失败: {e}")
            return SendResult(success=False)
    
    async def parse_event(self, raw_event: dict) -> Optional[PlatformEvent]:
        """解析原始事件"""
        if raw_event.get("type") != "message":
            return None
        
        return PlatformEvent(
            platform=self.platform,
            event_type=EventType.PRIVATE_MESSAGE,
            sender=SenderInfo(
                id=raw_event["user_id"],
                name=raw_event.get("username", "Unknown")
            ),
            content=MessageContent(
                text=raw_event.get("text", "")
            ),
            raw_event=raw_event
        )
    
    async def _connect(self):
        """连接逻辑（私有方法）"""
        # 建立 WebSocket 连接、HTTP 轮询等
        pass
    
    async def _on_platform_message(self, raw_event: dict):
        """收到平台消息时调用"""
        event = await self.parse_event(raw_event)
        if event:
            await self.emit_event(event)
```

### 4. 配置 schema.json（可选）

```json
[
  {
    "key": "api_url",
    "type": "string",
    "required": true,
    "description": "平台 API 地址"
  },
  {
    "key": "api_token",
    "type": "string",
    "required": true,
    "description": "API Token"
  },
  {
    "key": "timeout",
    "type": "number",
    "default": 30,
    "description": "请求超时（秒）"
  }
]
```

### 5. 启动适配器

```python
await manager.start_adapter(
    adapter_id="my_platform_1",
    adapter_type="my_platform",
    adapter_config={
        "api_url": "https://api.myplatform.com",
        "api_token": "your-token",
        "timeout": 30
    }
)
```

---

## AdapterEventBridge — 事件桥接

将适配器事件桥接到 EventBus。

**文件位置**：[core/adapter/integration.py](../../core/adapter/integration.py)

### 工作流程

```python
# 1. 适配器收到平台消息
raw_event = {"user_id": "123", "text": "你好"}

# 2. 适配器解析为 PlatformEvent
event = await adapter.parse_event(raw_event)

# 3. 适配器调用 emit_event
await adapter.emit_event(event)

# 4. AdapterEventBridge 收到回调
async def on_event(event: PlatformEvent, adapter_id: str):
    # 5. 转发到 EventBus
    bus.emit("platform_message", event, adapter_id=adapter_id)

# 6. 其他组件监听 EventBus
@bus.on("platform_message")
def handle_message(event: PlatformEvent, adapter_id: str):
    print(f"收到来自 {adapter_id} 的消息")
```

### 发送回复

```python
from core.adapter.integration import AdapterEventBridge

bridge = AdapterEventBridge(adapter_manager)

# 回复消息
await bridge.send_message(
    adapter_id="qq",          # 平台类型或实例名
    target_id="user_123",
    content=["你好！", "这是回复"],
    is_group=False
)

# 回复群消息
await bridge.send_message(
    adapter_id=event.platform.value,  # 使用原平台
    target_id=event.group_id or event.sender.id,
    content=["收到"],
    is_group=event.is_group_message()
)
```

---

## 错误处理

### 启动失败回滚

```python
try:
    await manager.start_adapter("qq_bot", config)
except Exception as e:
    # AdapterManager 自动回滚：
    # 1. 从 _adapters 移除
    # 2. 从 _enabled_adapters 移除
    # 3. 从 _platform_index 移除
    # 4. 调用 adapter.stop() 清理资源
    print(f"启动失败: {e}")
```

### 发送失败处理

```python
result = await manager.send_message(...)

if not result.success:
    if result.failed_files:
        # 部分文件发送失败
        print(f"以下文件未送达: {result.failed_files}")
    else:
        # 完全发送失败
        print("消息发送失败")
```

### 适配器错误隔离

```python
# 单个适配器崩溃不影响其他适配器
class MyAdapter(BaseAdapter):
    async def start(self):
        try:
            await self._connect()
        except Exception as e:
            self.on_error(f"连接失败: {e}")
            raise  # 启动失败抛出异常
    
    def on_error(self, error_msg: str):
        """错误回调（可重写）"""
        logger.error(f"[{self.platform.value}] {error_msg}")
        # 可选：发送告警、记录日志等
```

---

## 最佳实践

### 1. 配置管理

```python
# 推荐：使用配置文件
# data/config/platforms.yaml
qq:
  - id: "qq_bot_1"
    enabled: true
    ws_url: "ws://localhost:8080"

# 避免：硬编码配置
config = {"ws_url": "ws://localhost:8080"}
```

### 2. 错误处理

```python
# 推荐：详细的错误信息
try:
    await adapter.send_message(...)
except ConnectionError as e:
    self.on_error(f"连接断开: {e}")
except TimeoutError as e:
    self.on_error(f"发送超时: {e}")

# 避免：吞没所有错误
try:
    await adapter.send_message(...)
except:
    pass
```

### 3. 资源清理

```python
# 推荐：正确清理资源
async def stop(self):
    if self.websocket:
        await self.websocket.close()
    if self.task:
        self.task.cancel()
    self._running = False

# 避免：忘记清理
async def stop(self):
    self._running = False
```

### 4. 消息去重

```python
# 推荐：记录已处理的消息 ID
class MyAdapter(BaseAdapter):
    def __init__(self, *args):
        super().__init__(*args)
        self._processed_ids = set()
    
    async def parse_event(self, raw_event):
        msg_id = raw_event.get("message_id")
        if msg_id in self._processed_ids:
            return None  # 重复消息，忽略
        self._processed_ids.add(msg_id)
        return PlatformEvent(...)
```

---

## 性能考虑

### 连接池

对于 HTTP 适配器，使用连接池：

```python
import aiohttp

class HTTPAdapter(BaseAdapter):
    async def start(self):
        self.session = aiohttp.ClientSession()
    
    async def stop(self):
        await self.session.close()
    
    async def send_message(self, target_id, content, **kwargs):
        async with self.session.post(url, json=data) as resp:
            return SendResult(success=resp.status == 200)
```

### 批量发送

```python
# 推荐：批量发送（适配器支持时）
await manager.send_message(
    adapter_id="qq",
    target_id="group_123",
    text="消息1\n消息2\n消息3"
)

# 避免：多次单独发送
for msg in messages:
    await manager.send_message(...)
```

### 异步处理

```python
# 推荐：并发发送到多个平台
tasks = [
    manager.send_message("qq", target, text),
    manager.send_message("wechat_pc", target, text)
]
results = await asyncio.gather(*tasks)

# 避免：串行发送
await manager.send_message("qq", target, text)
await manager.send_message("wechat_pc", target, text)
```

---

## 调试技巧

### 查看原始事件

```python
@bus.on("platform_message")
def debug_event(event: PlatformEvent, adapter_id: str):
    print(f"原始事件: {event.raw_event}")
```

### 监控适配器状态

```python
# 定期检查适配器状态
async def monitor():
    while True:
        for adapter_id in manager.list_running_adapters():
            adapter = manager.get_adapter(adapter_id)
            print(f"{adapter_id}: running={adapter.is_running}")
        await asyncio.sleep(10)
```

### 消息追踪

```python
class TracingAdapter(BaseAdapter):
    async def send_message(self, target_id, content, **kwargs):
        start = time.time()
        result = await super().send_message(target_id, content, **kwargs)
        elapsed = time.time() - start
        logger.info(f"发送耗时: {elapsed:.3f}s, 成功: {result.success}")
        return result
```

---

## 与其他系统集成

### 与 Pipeline 集成

```python
# ReplyDeliverStage 通过 AdapterManager 发送回复
class ReplyDeliverStage(PipelineStage):
    async def process(self, ctx: PipelineContext):
        await adapter_manager.send_message(
            adapter_id=ctx.event.platform.value,
            target_id=ctx.target_id,
            text="\n".join(ctx.reply_content)
        )
```

### 与事件系统集成

```python
# AdapterEventBridge 监听 EventBus 发送请求
@bus.on("send_message")
async def on_send_request(adapter_id, target_id, text):
    await adapter_manager.send_message(adapter_id, target_id, text)
```

---

## 下一步

- [事件系统](event-system.md) — 适配器事件如何流转
- [Pipeline 系统](pipeline.md) — 消息处理流程
- [多智能体架构](multi-agent.md) — 消息如何被 LLM 处理
