# EventBus API 参考

EventBus 是 Tale-AI 的进程内事件发布/订阅系统，支持优先级、异步回调、一次性订阅。

**定义位置**: `core/bus/bus.py`

---

## 类 EventBus

### 构造函数

```python
def __init__(self):
    """创建一个新的 EventBus 实例
    
    Tale-AI 使用全局单例: from core.bus import bus
    """
```

---

## 订阅方法

### on()

```python
def on(self, event_name: str, callback: Callable, priority: int = 0) -> EventBus:
    """订阅事件（同步或异步回调均可）
    
    Args:
        event_name: 事件名（字符串）
        callback: 回调函数（支持同步函数和 async 函数）
        priority: 优先级（越大越先触发，默认 0）
        
    Returns:
        self（支持链式调用）
        
    注意:
        - 同一事件可注册多个回调，按优先级排序执行
        - 相同优先级按注册顺序执行
        - callback 异常不会中断其他回调，错误会记录到日志
    """
```

**参数详情**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `event_name` | `str` | - | 事件名，建议使用下划线分隔（如 `config_reloaded`） |
| `callback` | `Callable` | - | 回调函数，签名为 `(*args, **kwargs)` 或 `async (*args, **kwargs)` |
| `priority` | `int` | `0` | 优先级，数字越大越先执行。同优先级按注册顺序执行 |

**使用示例**:

```python
from core.bus import bus

# 同步回调
def on_config_reload():
    print("Config reloaded")

bus.on("config_reloaded", on_config_reload)

# 异步回调
async def on_message(text, sender):
    await save_to_db(text, sender)

bus.on("message_received", on_message)

# 带优先级（高优先级先执行）
bus.on("app_start", init_critical_services, priority=100)
bus.on("app_start", init_optional_features, priority=0)

# 链式调用
bus.on("event_a", handler_a).on("event_b", handler_b)
```

---

### once()

```python
def once(self, event_name: str, callback: Callable) -> EventBus:
    """订阅事件，仅触发一次后自动取消订阅
    
    Args:
        event_name: 事件名
        callback: 回调函数（同步）
        
    Returns:
        self（支持链式调用）
        
    注意:
        - 回调执行完毕后自动调用 off() 取消订阅
        - 适用于一次性初始化逻辑
    """
```

**使用示例**:

```python
from core.bus import bus

def on_first_message(text):
    print(f"First message: {text}")
    # 自动取消订阅，后续 message 事件不再触发

bus.once("message", on_first_message)
```

---

### aonce()

```python
def aonce(self, event_name: str, callback: Callable) -> EventBus:
    """订阅事件，仅触发一次后自动取消订阅（支持异步回调）
    
    Args:
        event_name: 事件名
        callback: 回调函数（同步或异步均可）
        
    Returns:
        self（支持链式调用）
        
    注意:
        - 回调可以是 async 函数或普通函数
        - 回调执行完毕后自动调用 off() 取消订阅
    """
```

**使用示例**:

```python
from core.bus import bus

async def on_first_startup():
    await init_database()
    await load_plugins()

bus.aonce("app_start", on_first_startup)
```

---

### off()

```python
def off(self, event_name: str, callback: Optional[Callable] = None) -> EventBus:
    """取消订阅事件
    
    Args:
        event_name: 事件名
        callback: 要取消的回调函数。如果为 None，则取消该事件的所有订阅
        
    Returns:
        self（支持链式调用）
        
    注意:
        - callback 必须是注册时的同一个函数对象（引用相同）
        - 取消不存在的订阅不会报错
    """
```

**使用示例**:

```python
from core.bus import bus

def handler(data):
    pass

# 订阅
bus.on("event", handler)

# 取消特定回调
bus.off("event", handler)

# 取消该事件的所有订阅
bus.off("event")
```

---

## 发布方法

### emit()

```python
def emit(self, event_name: str, *args, **kwargs) -> None:
    """触发同步事件
    
    Args:
        event_name: 事件名
        *args: 传递给回调的位置参数
        **kwargs: 传递给回调的关键字参数
        
    注意:
        - 按优先级顺序同步执行所有回调
        - 回调异常会记录到日志，但不会中断其他回调
        - 如果回调是 async 函数，不会 await（请用 aemit）
    """
```

**使用示例**:

```python
from core.bus import bus

# 无参数事件
bus.emit("app_shutdown")

# 带参数事件
bus.emit("message_received", text="Hello", sender="user123")

# 位置参数
bus.emit("calculation_done", 42, "success")
```

---

### aemit()

```python
async def aemit(self, event_name: str, *args, **kwargs) -> None:
    """触发异步事件，自动识别回调是否为协程函数
    
    Args:
        event_name: 事件名
        *args: 传递给回调的位置参数
        **kwargs: 传递给回调的关键字参数
        
    注意:
        - 按优先级顺序执行所有回调
        - 异步回调会 await，同步回调直接调用
        - 回调异常会记录到日志，但不会中断其他回调
    """
```

**使用示例**:

```python
from core.bus import bus

# 在 async 函数中触发
async def process_message(text):
    await bus.aemit("message_processing", text=text)
    # 所有 async 回调都已执行完毕

# 混合同步/异步回调
def sync_handler(text):
    print(f"Sync: {text}")

async def async_handler(text):
    await save_to_db(text)

bus.on("message_processing", sync_handler)
bus.on("message_processing", async_handler)

# aemit 会自动处理两种回调
await bus.aemit("message_processing", text="Hello")
```

---

## 内置事件列表

Tale-AI 核心系统使用的标准事件：

### 系统生命周期

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `config_reloaded` | 配置文件热重载完成 | 无 |

### 平台消息

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `platform_message` | 收到任意平台消息 | `PlatformEvent` |
| `private_message` | 收到私聊消息 | `PlatformEvent` |
| `group_message` | 收到群聊消息 | `PlatformEvent` |
| `qq_message` | 收到 QQ 消息 | `PlatformEvent` |
| `platform_notice` | 收到平台通知（加群、@等） | `PlatformEvent` |
| `wechat_moments_message` | 收到微信朋友圈消息 | 朋友圈数据 |

### Pipeline 钩子

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `pipeline_stage_before_{stage.name}` | Stage 执行前 | `PipelineContext` |
| `pipeline_stage_after_{stage.name}` | Stage 执行后 | `PipelineContext` |

**示例**:
- `pipeline_stage_before_build_user_input`
- `pipeline_stage_after_session_init`

### 计划系统

| 事件名 | 触发时机 | 参数 |
|--------|----------|------|
| `plan` | 请求生成计划 | `prompt: str` |

---

## 事件命名规范

推荐遵循以下命名规范：

1. **小写 + 下划线**: `config_reloaded`, `message_received`
2. **动作为过去式**: `config_reloaded`（而非 `config_reload`）
3. **层级分隔**: 使用下划线分隔作用域，如 `pipeline_stage_before_*`
4. **语义清晰**: 事件名应自解释，避免缩写

**推荐**:
- `user_login`, `message_sent`, `plugin_loaded`

**不推荐**:
- `usrLogin`, `msg_snd`, `plg_ld`

---

## 优先级机制

回调按以下规则排序执行：

1. **优先级从高到低**: `priority` 越大越先执行
2. **同优先级按注册顺序**: 先注册先执行
3. **默认优先级为 0**

**使用示例**:

```python
from core.bus import bus

# 执行顺序: critical -> normal -> cleanup
bus.on("shutdown", critical_cleanup, priority=100)
bus.on("shutdown", normal_cleanup, priority=0)
bus.on("shutdown", final_cleanup, priority=-10)
```

---

## 错误处理

回调函数中的异常会被捕获并记录到日志，不会影响其他回调执行。

```python
from core.bus import bus

def safe_handler(data):
    process(data)  # 可能抛出异常

def critical_handler(data):
    log(data)  # 即使 safe_handler 失败，仍会执行

bus.on("event", safe_handler)
bus.on("event", critical_handler)

# safe_handler 抛出异常，但 critical_handler 仍会执行
bus.emit("event", data)
```

**日志输出示例**:

```
ERROR - Error in event handler for event_name: ValueError: Invalid data
```

---

## 线程安全

EventBus 使用 `threading.RLock()` 保证线程安全：

- `on()`, `off()` 在注册/取消时持有锁
- `emit()`, `aemit()` 在读取监听器列表时持有锁，执行回调时释放锁

**注意**: 回调函数应避免阻塞操作，否则会影响事件处理性能。

---

## 完整示例

```python
from core.bus import bus

# ===== 订阅事件 =====

# 同步回调
def on_message(text, sender):
    print(f"{sender}: {text}")

bus.on("message", on_message)

# 异步回调
async def on_message_async(text, sender):
    await save_to_db(text, sender)

bus.on("message", on_message_async)

# 高优先级回调（先执行）
def validate_message(text, sender):
    if not text:
        raise ValueError("Empty message")

bus.on("message", validate_message, priority=10)

# 一次性回调
def on_first_message(text, sender):
    print("First message received!")

bus.once("message", on_first_message)

# ===== 触发事件 =====

# 同步触发（不会 await async 回调）
bus.emit("message", text="Hello", sender="Alice")

# 异步触发（会 await async 回调）
await bus.aemit("message", text="World", sender="Bob")

# ===== 取消订阅 =====

# 取消特定回调
bus.off("message", on_message)

# 取消所有订阅
bus.off("message")
```

---

## 与插件系统集成

插件可通过 `EventSubscriber` 协议订阅事件：

```python
from core.plugin.base import PluginBase, EventSubscriber

class MyPlugin(PluginBase, EventSubscriber):
    def get_event_subscriptions(self) -> Dict[str, Callable]:
        return {
            "config_reloaded": self.on_config_reload,
            "message": self.on_message,
        }
    
    def on_config_reload(self):
        print("Config reloaded")
    
    async def on_message(self, text, sender):
        await self.process_message(text, sender)
    
    def _activate(self):
        pass  # PluginManager 自动注册 get_event_subscriptions 返回的事件
    
    def _deactivate(self):
        pass  # PluginManager 自动取消订阅
```

---

## 设计原则

1. **轻量级**: 纯内存实现，无外部依赖
2. **灵活性**: 支持同步/异步回调混合
3. **容错性**: 回调异常不影响其他回调
4. **可扩展**: 插件可通过 EventBus 扩展系统功能
5. **可观测**: 错误日志便于调试

---

## 最佳实践

1. **避免循环依赖**: 回调中不要再次触发同一事件
2. **异步优先**: 对于 I/O 密集操作，使用 async 回调 + aemit
3. **优先级分层**: 关键逻辑使用高优先级（如参数验证）
4. **合理命名**: 事件名应语义清晰，遵循命名规范
5. **及时取消**: 不再需要的订阅应及时 off，避免内存泄漏
