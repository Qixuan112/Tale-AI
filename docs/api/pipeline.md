# Pipeline API 参考

Pipeline 是 Tale-AI 的消息处理管道系统，将单体 `_handle_respond_message` 拆分为可组合的 Stage。

## 核心类

### PipelineContext

管道执行上下文，贯穿所有 Stage 的共享状态。

**定义位置**: `core/pipeline/context.py`

#### 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| **输入（只读）** |
| `processed` | `ProcessedMessage` | - | 必填。已处理的平台消息 |
| `adapter_instance` | `Optional[str]` | `None` | 适配器实例名 |
| **会话信息** |
| `sid` | `Optional[str]` | `None` | 会话 ID（格式：`platform:type:target_id`） |
| `session_enabled` | `bool` | `True` | 会话是否启用 |
| `is_group` | `bool` | `False` | 是否为群聊 |
| `target_id` | `str` | `""` | 目标 ID（群 ID 或用户 ID） |
| `platform_name` | `str` | `""` | 平台标识（如 `qq`, `wechat`） |
| **用户输入构建** |
| `user_text` | `str` | `""` | 格式化后的用户消息（含 `[At xxx]` `[Reply xxx]`） |
| `persist_content` | `str` | `""` | 落库用纯净原文（不含上下文/VLM 结果） |
| `user_input` | `str` | `""` | 最终喂给 LLM 的完整 prompt（含元数据/历史/VLM） |
| **跨会话消息** |
| `inbox_msgs` | `List[Dict]` | `[]` | 来自其他会话的消息 |
| `accessible_sessions` | `List[str]` | `[]` | 可通信会话列表 |
| **LLM 调用** |
| `chatllm_reply` | `Optional[str]` | `None` | ChatLLM 原始回复 |
| `parsed` | `Optional[Dict]` | `None` | 解析后的 XML 结构 |
| **消息发送** |
| `messages_to_send` | `List[Any]` | `[]` | 待发送消息列表 |
| `failed_files` | `List[str]` | `[]` | 发送失败的文件路径 |
| **控制流** |
| `should_stop` | `bool` | `False` | 提前终止标志（后续 Stage 不执行，除非 `always_run`） |
| `skip_reply` | `bool` | `False` | AI 主动选择不回复（`<msg></msg>`） |
| **扩展字段** |
| `extra` | `Dict[str, Any]` | `{}` | 插件使用的自定义字段 |

#### 方法

```python
def stop(self) -> None:
    """设置终止标志，后续 Stage（非 always_run）不再执行"""
```

---

### PipelineStage

管道阶段抽象基类，每个 Stage 实现一个独立职责。

**定义位置**: `core/pipeline/stage.py`

#### 构造函数

```python
def __init__(self, order: int, name: str, always_run: bool = False):
    """
    Args:
        order: 执行顺序（数字越小越早执行）
        name: Stage 名称（用于日志和事件）
        always_run: 是否总是执行（即使前面 Stage 设置了 stop）
    """
```

#### 抽象方法

```python
@abstractmethod
async def process(self, ctx: PipelineContext) -> None:
    """处理上下文（子类必须实现）
    
    Args:
        ctx: PipelineContext 实例
        
    Raises:
        Exception: 处理失败时抛出异常
    """
```

#### 钩子方法

```python
async def on_error(self, ctx: PipelineContext, error: Exception) -> bool:
    """错误处理钩子（可选重写）
    
    Args:
        ctx: PipelineContext 实例
        error: 捕获的异常
        
    Returns:
        True: 已恢复，继续执行后续 Stage
        False: 无法恢复，终止管道（默认）
    """
```

---

### MessagePipeline

消息处理管道抽象基类。

**定义位置**: `core/pipeline/base.py`

#### 方法

```python
def add_stage(self, stage: PipelineStage) -> None:
    """注册一个 Stage（自动按 order 排序）
    
    Args:
        stage: PipelineStage 实例
    """

def get_stages(self) -> List[PipelineStage]:
    """获取所有 Stage（按 order 排序）
    
    Returns:
        Stage 列表的副本
    """

@abstractmethod
async def execute(self, ctx: PipelineContext) -> PipelineContext:
    """执行管道（子类必须实现）
    
    Args:
        ctx: 管道上下文
        
    Returns:
        处理后的上下文
        
    Raises:
        Exception: 管道执行失败
    """
```

---

### StandardPipeline

标准管道实现，顺序执行 Stage，支持插件 hook 和错误恢复。

**定义位置**: `core/pipeline/standard.py`

#### 构造函数

```python
def __init__(self, bus=None):
    """初始化标准管道
    
    Args:
        bus: EventBus 实例，用于发送插件 hook 事件（可选）
    """
```

#### 方法

```python
async def execute(self, ctx: PipelineContext) -> PipelineContext:
    """执行管道
    
    按 order 顺序执行所有 Stage，每个 Stage 前后发送事件供插件 hook：
    - 前置事件: pipeline_stage_before_{stage.name}
    - 后置事件: pipeline_stage_after_{stage.name}
    
    Args:
        ctx: 管道上下文
        
    Returns:
        处理后的上下文
        
    Raises:
        Exception: Stage 执行失败且无法恢复时抛出
    """
```

**执行逻辑**:
1. 遍历所有 Stage（按 `order` 排序）
2. 检查终止标志：`ctx.should_stop == True` 且 `stage.always_run == False` 时跳过
3. 发送前置事件：`pipeline_stage_before_{stage.name}`
4. 执行 `stage.process(ctx)`
5. 发生异常时调用 `stage.on_error(ctx, e)`，返回 `False` 则终止管道
6. 发送后置事件：`pipeline_stage_after_{stage.name}`

---

## 标准 Stage

### BuildUserInputStage

**Order**: 100  
**职责**: 构建用户输入，格式化消息（`[At xxx]` `[Reply xxx]` 内容）

**定义位置**: `core/pipeline/stages/build_user_input.py`

#### 输入字段

| 字段 | 说明 |
|------|------|
| `ctx.processed` | 原始消息 |
| `ctx.adapter_instance` | 适配器实例名（可选） |

#### 输出字段

| 字段 | 说明 |
|------|------|
| `ctx.platform_name` | 平台标识（从 `processed.platform` 提取） |
| `ctx.is_group` | 是否为群聊 |
| `ctx.target_id` | 目标 ID（群 ID 或用户 ID） |
| `ctx.user_text` | 格式化消息：`[At xxx] [Reply xxx] 内容` |
| `ctx.persist_content` | 纯净原文（用于落库） |

---

### NameMappingStage

**Order**: 200  
**职责**: 维护昵称→ID 映射表（按群分组），供发送时解析 @ 用

**定义位置**: `core/pipeline/stages/name_mapping.py`

#### 构造函数

```python
def __init__(self, name_to_id_cache: BoundedCache, id_sanitizer):
    """
    Args:
        name_to_id_cache: 昵称→ID 映射缓存
        id_sanitizer: ID 脱敏器
    """
```

#### 输入字段

| 字段 | 说明 |
|------|------|
| `ctx.processed.sender_name` | 发送者昵称 |
| `ctx.processed.sender_id` | 发送者 ID |
| `ctx.processed.group_id` | 群 ID（可选） |

#### 副作用

更新 `name_to_id_cache`，键为 `group_id` 或 `"_private"`，值为 `{昵称: 脱敏后的ID}`。

---

### SessionInitStage

**Order**: 300  
**职责**: 会话初始化，构造 sid，加载历史，消费跨会话 inbox

**定义位置**: `core/pipeline/stages/session_init.py`

#### 构造函数

```python
def __init__(
    self,
    session_manager: Optional[Any] = None,
    chat_llm: Optional[Any] = None,
    bridge: Optional[Any] = None
):
    """
    Args:
        session_manager: SessionManager 实例
        chat_llm: ChatLLM 实例（用于 set_session）
        bridge: BridgeState 实例（跨会话消息）
    """
```

#### 输入字段

| 字段 | 说明 |
|------|------|
| `ctx.is_group` | 会话类型（由 BuildUserInputStage 设置） |
| `ctx.target_id` | 目标 ID |
| `ctx.processed.platform` | 平台枚举 |

#### 输出字段

| 字段 | 说明 |
|------|------|
| `ctx.sid` | 会话 ID（格式：`platform:type:target_id`） |
| `ctx.session_enabled` | 会话是否启用 |
| `ctx.inbox_msgs` | 跨会话消息列表 |
| `ctx.accessible_sessions` | 可通信会话列表 |

#### 副作用

- 调用 `chat_llm.set_session(sid, load_history=...)` 加载历史
- 调用 `bridge.consume(sid)` 消费跨会话消息

---

### ContextBuildStage

**Order**: 400  
**职责**: 整合元数据、图片识别、历史上下文、跨会话消息，构建最终 `user_input`

**定义位置**: `core/pipeline/stages/context_build.py`

#### 构造函数

```python
def __init__(
    self,
    context_builder: ContextBuilder,
    context_buffer: Optional[Dict] = None
):
    """
    Args:
        context_builder: ContextBuilder 实例（已配置 MetadataBuilder/MediaRecognizer/HistoryProvider）
        context_buffer: 上下文缓冲区（BoundedCache，非持久化模式用）
    """
```

#### 输入字段

| 字段 | 说明 |
|------|------|
| `ctx.processed` | 原始消息 |
| `ctx.platform_name` | 平台标识 |
| `ctx.session_enabled` | 会话是否启用 |
| `ctx.inbox_msgs` | 跨会话消息 |
| `ctx.accessible_sessions` | 可通信会话列表 |

#### 输出字段

| 字段 | 说明 |
|------|------|
| `ctx.user_input` | 最终喂给 LLM 的完整 prompt（含元数据/历史/VLM/跨会话消息） |

#### 构建流程

1. 调用 `context_builder.build_input()` 构建基础上下文（元数据 + VLM + 历史）
2. 追加跨会话消息（`inbox_msgs`）
3. 追加可通信会话列表（`accessible_sessions`）
4. 组装最终 `user_input`

---

## 使用示例

### 创建自定义 Stage

```python
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext

class MyCustomStage(PipelineStage):
    def __init__(self):
        super().__init__(order=500, name="my_custom_stage")
    
    async def process(self, ctx: PipelineContext) -> None:
        # 读取上游 Stage 的输出
        user_input = ctx.user_input
        
        # 执行自定义逻辑
        result = await my_async_processing(user_input)
        
        # 写入上下文供下游 Stage 使用
        ctx.extra["my_result"] = result
        
        # 可选：提前终止管道
        if should_abort:
            ctx.stop()
    
    async def on_error(self, ctx: PipelineContext, error: Exception) -> bool:
        # 尝试恢复错误
        if isinstance(error, RecoverableError):
            ctx.extra["recovered"] = True
            return True  # 继续执行
        return False  # 终止管道
```

### 使用 StandardPipeline

```python
from core.pipeline.standard import StandardPipeline
from core.pipeline.context import PipelineContext
from core.bus import bus

# 创建管道
pipeline = StandardPipeline(bus=bus)

# 注册 Stage（自动按 order 排序）
pipeline.add_stage(BuildUserInputStage())
pipeline.add_stage(SessionInitStage(session_manager, chat_llm, bridge))
pipeline.add_stage(MyCustomStage())

# 执行管道
ctx = PipelineContext(processed=processed_message)
result_ctx = await pipeline.execute(ctx)
```

### 订阅 Stage 事件

```python
from core.bus import bus

def on_stage_before(ctx):
    print(f"Before custom stage: {ctx.user_text}")

def on_stage_after(ctx):
    print(f"After custom stage: {ctx.extra.get('my_result')}")

bus.on("pipeline_stage_before_my_custom_stage", on_stage_before)
bus.on("pipeline_stage_after_my_custom_stage", on_stage_after)
```

---

## 设计原则

1. **单一职责**: 每个 Stage 只做一件事，便于单元测试
2. **顺序执行**: Stage 按 `order` 排序，从小到大执行
3. **上下文传递**: 通过 `PipelineContext` 共享状态，避免全局变量
4. **错误恢复**: Stage 可实现 `on_error` 尝试恢复，避免整个管道崩溃
5. **可观测性**: 通过 EventBus 发送前后置事件，支持插件 hook 和监控
6. **提前终止**: 通过 `ctx.stop()` 优雅终止管道，`always_run` Stage 仍会执行
