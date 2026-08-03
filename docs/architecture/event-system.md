# 事件系统

## 概述

Tale-AI 使用 **EventBus（事件总线）** 作为核心通信机制，实现组件间的解耦。所有模块通过发布/订阅模式交互，无需直接依赖。

## 设计目标

- **解耦** — 组件间无需相互引用，通过事件通信
- **扩展** — 插件可监听任意事件，无需修改核心代码
- **灵活** — 支持同步/异步、优先级、一次性订阅
- **可靠** — 错误隔离，单个监听器失败不影响其他

---

## 核心组件

### EventBus

单例事件总线，全局唯一。

```python
from core.bus import bus

# 订阅事件
bus.on("message_received", handle_message)

# 发布事件
bus.emit("message_received", message_data)

# 取消订阅
bus.off("message_received", handle_message)
```

**文件位置**：[core/bus/bus.py](../../core/bus/bus.py)

---

## 基础用法

### 订阅事件

#### 同步监听器

```python
from core.bus import bus

def on_message(event):
    print(f"收到消息: {event.content.text}")

# 注册监听器
bus.on("platform_message", on_message)
```

#### 异步监听器

```python
from core.bus import bus

async def on_message_async(event):
    await process_message(event)

# 同样使用 on() 注册（自动识别）
bus.on("platform_message", on_message_async)

# 触发时使用 aemit()
await bus.aemit("platform_message", event)
```

### 发布事件

#### 同步发布

```python
# 位置参数
bus.emit("user_login", user_id, timestamp)

# 关键字参数
bus.emit("config_changed", config_type="services", reload_time=time.time())
```

#### 异步发布

```python
# 自动识别监听器类型并调用
await bus.aemit("message_sent", message, target_id="user_123")

# 同步监听器：直接调用
# 异步监听器：await 调用
```

### 取消订阅

```python
# 取消特定监听器
bus.off("platform_message", on_message)

# 取消该事件的所有监听器
bus.off("platform_message")
```

---

## 高级特性

### 优先级

监听器可以指定优先级，数字越大越先执行：

```python
# 高优先级（先执行）
bus.on("platform_message", auth_check, priority=100)

# 中优先级（默认）
bus.on("platform_message", log_message, priority=0)

# 低优先级（后执行）
bus.on("platform_message", analytics, priority=-10)
```

**执行顺序**：
```
auth_check (100) → log_message (0) → analytics (-10)
```

**应用场景**：
- **权限检查** — 高优先级，先验证权限
- **日志记录** — 中优先级，记录事件
- **统计分析** — 低优先级，不影响主流程

### 一次性监听

#### 同步版本

```python
def on_first_message(event):
    print("首次收到消息（仅触发一次）")

bus.once("platform_message", on_first_message)

# 第一次触发后自动取消订阅
bus.emit("platform_message", event1)  # 会触发
bus.emit("platform_message", event2)  # 不会触发
```

#### 异步版本

```python
async def on_first_message_async(event):
    await setup_session(event)

bus.aonce("platform_message", on_first_message_async)

# 异步发布
await bus.aemit("platform_message", event)
```

**应用场景**：
- 首次启动初始化
- 延迟加载资源
- 等待特定条件触发

---

## 事件列表

### 平台消息事件

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `platform_message` | 收到平台消息 | `event: PlatformEvent, adapter_id: str` |
| `message_sent` | 消息发送成功 | `adapter_id: str, target_id: str, content: MessageContent` |
| `message_failed` | 消息发送失败 | `adapter_id: str, error: Exception` |

**示例**：
```python
from core.adapter.event import PlatformEvent

@bus.on("platform_message")
def handle_message(event: PlatformEvent, adapter_id: str):
    print(f"[{adapter_id}] {event.sender.name}: {event.content.text}")
```

### Pipeline 事件

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `pipeline_stage_before_{stage_name}` | Stage 执行前 | `ctx: PipelineContext` |
| `pipeline_stage_after_{stage_name}` | Stage 执行后 | `ctx: PipelineContext` |
| `pipeline_error` | Pipeline 执行失败 | `ctx: PipelineContext, error: Exception` |

**示例**：
```python
@bus.on("pipeline_stage_before_llm_call")
def before_llm(ctx):
    print(f"准备调用 LLM，上下文长度：{len(ctx.context_messages)}")

@bus.on("pipeline_stage_after_llm_call")
def after_llm(ctx):
    print(f"LLM 响应：{ctx.llm_response[:100]}...")
```

**所有 Pipeline Stage 事件**：
- `pipeline_stage_before_build_user_input`
- `pipeline_stage_after_build_user_input`
- `pipeline_stage_before_name_mapping`
- `pipeline_stage_after_name_mapping`
- `pipeline_stage_before_session_init`
- `pipeline_stage_after_session_init`
- `pipeline_stage_before_context_build`
- `pipeline_stage_after_context_build`
- `pipeline_stage_before_llm_call`
- `pipeline_stage_after_llm_call`
- `pipeline_stage_before_message_parse`
- `pipeline_stage_after_message_parse`
- `pipeline_stage_before_tool_execute`
- `pipeline_stage_after_tool_execute`
- `pipeline_stage_before_reply_deliver`
- `pipeline_stage_after_reply_deliver`

### 配置事件

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `config_reloaded` | 配置文件重新加载 | `config_type: str` (可选) |

**示例**：
```python
@bus.on("config_reloaded")
def on_config_reload(config_type=None):
    if config_type == "services":
        # 重新初始化 LLM 客户端
        reinit_llm()
    elif config_type == "platforms":
        # 重启适配器
        restart_adapters()
```

### 适配器事件

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `adapter_started` | 适配器启动成功 | `adapter_id: str, platform: str` |
| `adapter_stopped` | 适配器停止 | `adapter_id: str` |
| `adapter_error` | 适配器错误 | `adapter_id: str, error: Exception` |

### 会话事件

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `session_created` | 新建会话 | `session_id: str` |
| `session_loaded` | 加载会话 | `session_id: str` |
| `session_cleared` | 清空会话 | `session_id: str` |

### 工具事件

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `tool_registered` | 注册新工具 | `tool_name: str` |
| `tool_called` | 调用工具 | `tool_name: str, parameters: dict` |
| `tool_result` | 工具返回结果 | `tool_name: str, result: Any` |

### 日程事件

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `plan` | 请求生成/修改日程 | `prompt: str` |
| `plan_generated` | 日程生成完成 | `plan: DailyPlan` |
| `event_added` | 添加日程条目 | `entry: DiaryEntry` |

---

## 插件集成

### EventSubscriber 协议

插件通过 `EventSubscriber` 协议订阅事件：

```python
# plugins/my_plugin/plugin.py

class MyPlugin:
    def subscribe_events(self, bus):
        """EventSubscriber 协议要求实现此方法"""
        bus.on("platform_message", self.on_message, priority=10)
        bus.on("tool_called", self.on_tool_call)
    
    def on_message(self, event, adapter_id):
        print(f"插件收到消息: {event.content.text}")
    
    def on_tool_call(self, tool_name, parameters):
        print(f"工具调用: {tool_name}({parameters})")

def load(manager):
    plugin = MyPlugin()
    # 插件管理器自动调用 subscribe_events
    return plugin
```

### Hook Pipeline Stage

监听 Pipeline Stage 的前后事件：

```python
# plugins/audit_plugin/plugin.py

class AuditPlugin:
    def subscribe_events(self, bus):
        # 在 LLM 调用前记录
        bus.on("pipeline_stage_before_llm_call", self.before_llm)
        
        # 在 LLM 调用后审计
        bus.on("pipeline_stage_after_llm_call", self.after_llm)
    
    def before_llm(self, ctx):
        self.start_time = time.time()
        self.log_audit("llm_call_start", {
            "user_input": ctx.user_input,
            "session_id": ctx.session_id
        })
    
    def after_llm(self, ctx):
        elapsed = time.time() - self.start_time
        self.log_audit("llm_call_complete", {
            "response_length": len(ctx.llm_response),
            "elapsed_ms": elapsed * 1000
        })
```

### 自定义事件

插件可以发布自定义事件：

```python
class MyPlugin:
    def process_data(self, data):
        # 发布自定义事件
        bus.emit("my_plugin_data_processed", data, result="success")

# 其他插件可以监听
@bus.on("my_plugin_data_processed")
def on_custom_event(data, result):
    print(f"自定义事件触发: {result}")
```

---

## 错误处理

### 错误隔离

单个监听器失败不影响其他监听器：

```python
@bus.on("platform_message")
def listener1(event):
    raise Exception("监听器1失败")  # 仅记录错误

@bus.on("platform_message")
def listener2(event):
    print("监听器2正常执行")  # 继续执行

bus.emit("platform_message", event)
# 输出:
# ERROR: Error in event handler for platform_message: 监听器1失败
# 监听器2正常执行
```

### 异步错误处理

```python
@bus.on("platform_message")
async def async_listener(event):
    raise Exception("异步监听器失败")

await bus.aemit("platform_message", event)
# 错误被捕获并记录，不会中断其他监听器
```

---

## 最佳实践

### 1. 命名规范

```python
# 推荐：清晰的命名（动词形式）
bus.emit("message_received", event)
bus.emit("config_reloaded", config_type)
bus.emit("tool_called", tool_name)

# 避免：模糊的命名（名词形式）
bus.emit("message", event)
bus.emit("config", config_type)
bus.emit("tool", tool_name)
```

### 2. 事件粒度

```python
# 推荐：细粒度事件（便于精确监听）
bus.emit("pipeline_stage_before_llm_call", ctx)
bus.emit("pipeline_stage_after_llm_call", ctx)

# 避免：粗粒度事件（难以区分具体阶段）
bus.emit("pipeline_stage", stage_name, ctx)
```

### 3. 参数传递

```python
# 推荐：传递必要的上下文
bus.emit("message_sent", adapter_id="qq", target_id="user_123", content=content)

# 避免：传递过多无关数据
bus.emit("message_sent", entire_application_state)
```

### 4. 避免循环事件

```python
# 危险：可能导致无限循环
@bus.on("message_received")
def handle_message(event):
    # 处理后又发送消息，触发 message_received
    bus.emit("message_received", new_event)

# 推荐：使用不同事件名
@bus.on("message_received")
def handle_message(event):
    process(event)
    bus.emit("message_processed", result)
```

### 5. 清理监听器

```python
class MyComponent:
    def __init__(self):
        self.handler = lambda e: self.handle(e)
        bus.on("platform_message", self.handler)
    
    def shutdown(self):
        # 清理时取消订阅
        bus.off("platform_message", self.handler)
```

---

## 性能考虑

### 监听器数量

EventBus 采用线性遍历，时间复杂度 O(n)：

| 监听器数量 | 触发耗时 |
|------------|----------|
| 1-10 | <1 微秒 |
| 10-100 | 1-10 微秒 |
| 100-1000 | 10-100 微秒 |

**建议**：单个事件的监听器数量控制在 100 以内。

### 同步 vs 异步

```python
# 同步发布（阻塞）
bus.emit("event", data)  # 等待所有监听器执行完

# 异步发布（非阻塞）
await bus.aemit("event", data)  # 并发执行异步监听器
```

**选择建议**：
- **关键路径** — 使用同步确保执行顺序
- **后台任务** — 使用异步提高吞吐量

### 避免重复订阅

```python
# 避免：每次调用都注册新监听器（内存泄漏）
def init():
    bus.on("platform_message", handle_message)

# 推荐：只注册一次（模块级）
bus.on("platform_message", handle_message)

def init():
    pass
```

---

## 调试技巧

### 监听所有事件

```python
# 全局监听器（调试用）
original_emit = bus.emit

def debug_emit(event_name, *args, **kwargs):
    print(f"[EventBus] {event_name} ({len(args)} args, {len(kwargs)} kwargs)")
    return original_emit(event_name, *args, **kwargs)

bus.emit = debug_emit
```

### 统计事件频率

```python
from collections import Counter

event_counter = Counter()

original_emit = bus.emit
def counting_emit(event_name, *args, **kwargs):
    event_counter[event_name] += 1
    return original_emit(event_name, *args, **kwargs)

bus.emit = counting_emit

# 打印统计
print(event_counter.most_common(10))
```

### 监听器追踪

```python
# 查看某事件的所有监听器
event_name = "platform_message"
listeners = bus._listeners.get(event_name, [])

print(f"{event_name} 监听器列表:")
for priority, seq, callback in listeners:
    print(f"  优先级 {priority}: {callback.__name__}")
```

---

## 与其他系统集成

### 与 Pipeline 集成

```python
# Pipeline 在每个 Stage 前后发送事件
class StandardPipeline:
    async def execute(self, ctx):
        for stage in self.stages:
            # Stage 执行前
            bus.emit(f"pipeline_stage_before_{stage.name}", ctx)
            
            # 执行 Stage
            await stage.process(ctx)
            
            # Stage 执行后
            bus.emit(f"pipeline_stage_after_{stage.name}", ctx)
```

### 与适配器集成

```python
# AdapterEventBridge 将平台消息转发到 EventBus
class AdapterEventBridge:
    async def on_event(self, event: PlatformEvent, adapter_id: str):
        bus.emit("platform_message", event, adapter_id=adapter_id)
```

### 与插件集成

```python
# PluginManager 自动调用插件的 subscribe_events
class PluginManager:
    def load_plugin(self, plugin):
        if hasattr(plugin, 'subscribe_events'):
            plugin.subscribe_events(bus)
```

---

## 架构图

```
┌─────────────────────────────────────────────────────┐
│                    EventBus                          │
│              (单例，全局唯一)                         │
└───────────┬─────────────────────────────────────────┘
            │
   ┌────────┴────────┐
   │   订阅者注册表   │
   │  {event_name:   │
   │   [(priority,   │
   │     seq,        │
   │     callback)]  │
   │  }              │
   └────────┬────────┘
            │
    ┌───────┴────────┐
    │                │
    ▼                ▼
┌─────────┐    ┌──────────┐
│ 同步调用 │    │ 异步调用  │
│  emit() │    │ aemit()  │
└────┬────┘    └────┬─────┘
     │              │
     ▼              ▼
  按优先级         按优先级
  顺序执行         并发执行
     │              │
     ▼              ▼
┌─────────────────────────┐
│    监听器执行            │
│  • 错误隔离              │
│  • 自动识别同步/异步      │
│  • 一次性监听自动注销     │
└─────────────────────────┘
```

---

## 事件驱动架构优势

### 传统耦合架构

```python
# 紧耦合示例
class MessageHandler:
    def __init__(self, logger, analytics, notifier):
        self.logger = logger
        self.analytics = analytics
        self.notifier = notifier
    
    def handle(self, message):
        self.logger.log(message)
        self.analytics.track(message)
        self.notifier.notify(message)
```

### 事件驱动架构

```python
# 解耦示例
class MessageHandler:
    def handle(self, message):
        bus.emit("message_received", message)

# 各组件独立订阅
bus.on("message_received", logger.log)
bus.on("message_received", analytics.track)
bus.on("message_received", notifier.notify)
```

**优势**：
- MessageHandler 无需知道谁需要消息
- 新增/删除功能无需修改 MessageHandler
- 各组件可以独立测试

---

## 下一步

- [多智能体架构](multi-agent.md) — 智能体间通过事件协作
- [Pipeline 系统](pipeline.md) — Pipeline Stage 的事件 hook
- [适配器架构](adapters.md) — 平台消息的事件转发
- [插件开发](../development/plugin-development.md) — 通过事件扩展功能
