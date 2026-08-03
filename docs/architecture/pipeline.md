# Pipeline 系统

## 概述

Pipeline 是 Tale-AI 的消息处理核心，采用**责任链模式**将消息处理流程拆分为多个独立的 Stage（阶段）。每个 Stage 专注于单一职责，通过 `PipelineContext` 传递数据。

## 设计目标

- **模块化** — 每个处理阶段独立封装，易于测试和维护
- **可扩展** — 插件可以注入自定义 Stage 或 hook 现有 Stage
- **错误恢复** — 每个 Stage 可以定义错误恢复策略
- **性能监控** — 自动记录每个 Stage 的耗时

## 核心组件

### PipelineContext

管道上下文，携带整个处理流程所需的所有数据。

```python
from core.pipeline.context import PipelineContext

ctx = PipelineContext()
ctx.event = platform_event       # 平台事件
ctx.user_input = "你好"          # 用户输入
ctx.session_id = "qq_12345"      # 会话 ID
ctx.llm_response = None          # LLM 响应
ctx.reply_content = []           # 回复内容
ctx.should_stop = False          # 终止标志
```

**核心字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `event` | `PlatformEvent` | 原始平台事件 |
| `user_input` | `str` | 用户输入文本 |
| `session_id` | `str` | 会话唯一标识 |
| `mapped_names` | `dict` | 名称映射结果 |
| `session_history` | `list` | 会话历史记录 |
| `context_messages` | `list` | LLM 上下文消息 |
| `llm_response` | `str` | LLM 原始响应 |
| `parsed_msg` | `ParsedMessage` | 解析后的消息 |
| `tool_results` | `list` | 工具调用结果 |
| `reply_content` | `list` | 最终回复内容 |
| `should_stop` | `bool` | 终止标志（用于提前退出） |

### PipelineStage

单个处理阶段的抽象基类。

```python
from core.pipeline.stage import PipelineStage

class MyStage(PipelineStage):
    def __init__(self):
        super().__init__(
            name="my_stage",
            order=100,           # 执行顺序（越小越早）
            always_run=False     # 是否无视终止标志
        )
    
    async def process(self, ctx: PipelineContext) -> None:
        # 处理逻辑
        ctx.user_input = ctx.user_input.strip()
    
    async def on_error(self, ctx: PipelineContext, error: Exception) -> bool:
        # 错误恢复逻辑
        # 返回 True 表示已恢复，继续执行
        # 返回 False 表示无法恢复，终止管道
        return False
```

**关键参数**：

- `name` — Stage 名称（用于日志和 hook）
- `order` — 执行顺序（数字越小越早执行）
- `always_run` — 是否无视 `ctx.should_stop` 强制执行

### MessagePipeline

管道抽象基类，管理 Stage 的注册和执行。

```python
from core.pipeline.base import MessagePipeline
from core.pipeline.standard import StandardPipeline

# 创建标准管道
pipeline = StandardPipeline(bus=event_bus)

# 注册 Stage
pipeline.add_stage(BuildUserInputStage())
pipeline.add_stage(NameMappingStage())
pipeline.add_stage(SessionInitStage())

# 执行管道
ctx = PipelineContext()
ctx.event = platform_event
result_ctx = await pipeline.execute(ctx)
```

### StandardPipeline

标准管道实现，提供以下功能：

1. **顺序执行** — 按 `order` 排序执行所有 Stage
2. **插件 Hook** — 在每个 Stage 前后发送事件
   - `pipeline_stage_before_{stage_name}`
   - `pipeline_stage_after_{stage_name}`
3. **错误恢复** — 调用 Stage 的 `on_error` 方法
4. **提前终止** — 支持 `ctx.should_stop` 标志
5. **性能监控** — 记录每个 Stage 的执行时间

## 标准 Pipeline 流程

Tale-AI 的标准消息处理管道包含 8 个 Stage：

```
┌─────────────────────────────────────────────────────────────┐
│                     StandardPipeline                        │
└─────────────────────────────────────────────────────────────┘
                            │
    ┌───────────────────────┼───────────────────────┐
    │                       │                       │
    ▼                       ▼                       ▼
┌─────────┐          ┌─────────┐          ┌─────────────┐
│  Build  │─────────▶│  Name   │─────────▶│   Session   │
│  User   │          │ Mapping │          │    Init     │
│  Input  │          │         │          │             │
└─────────┘          └─────────┘          └─────────────┘
  order=10             order=20              order=30
                                                  │
                                                  ▼
                                          ┌─────────────┐
                                          │   Context   │
                                          │    Build    │
                                          │             │
                                          └─────────────┘
                                              order=40
                                                  │
    ┌─────────────────────────────────────────────┼─────────┐
    │                                             │         │
    ▼                                             ▼         ▼
┌─────────┐                                ┌──────────┐  ┌────────┐
│   LLM   │───────────────────────────────▶│ Message  │  │  Tool  │
│  Call   │                                │  Parse   │─▶│Execute │
│         │                                │          │  │        │
└─────────┘                                └──────────┘  └────────┘
  order=50                                   order=60     order=70
                                                             │
                                                             ▼
                                                      ┌────────────┐
                                                      │   Reply    │
                                                      │  Deliver   │
                                                      │            │
                                                      └────────────┘
                                                        order=80
```

### 1. BuildUserInputStage (order=10)

**职责**：从 `PlatformEvent` 中提取用户输入文本。

```python
# 输入
ctx.event = PlatformEvent(...)

# 输出
ctx.user_input = "你好，今天天气怎么样？"
```

### 2. NameMappingStage (order=20)

**职责**：将消息中的 @mention 映射为角色名称。

```python
# 输入
ctx.user_input = "@Bot 你好"

# 输出
ctx.mapped_names = {"@Bot": "Tali"}
ctx.user_input = "@Tali 你好"
```

### 3. SessionInitStage (order=30)

**职责**：初始化或加载会话历史。

```python
# 输出
ctx.session_id = "qq_12345"
ctx.session_history = [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
    # ...
]
```

### 4. ContextBuildStage (order=40)

**职责**：构建 LLM 上下文（system prompt + 历史 + 当前输入）。

```python
# 输出
ctx.context_messages = [
    {"role": "system", "content": "你是 Tali..."},
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
    {"role": "user", "content": "今天天气怎么样？"},
]
```

### 5. LLMCallStage (order=50)

**职责**：调用 ChatLLM 获取响应。

```python
# 输入
ctx.context_messages = [...]

# 输出
ctx.llm_response = "<msg>让我查一下天气</msg><tool>weather_query</tool>"
```

### 6. MessageParseStage (order=60)

**职责**：解析 LLM 响应中的 XML 标签。

```python
# 输入
ctx.llm_response = "<msg>让我查一下天气</msg><tool>weather_query</tool>"

# 输出
ctx.parsed_msg = ParsedMessage(
    text_parts=["让我查一下天气"],
    tool_calls=["weather_query"],
    plan_requests=[],
    act_requests=[]
)
```

### 7. ToolExecuteStage (order=70)

**职责**：执行工具调用（如果存在 `<tool>` 标签）。

```python
# 输入
ctx.parsed_msg.tool_calls = ["weather_query"]

# 输出
ctx.tool_results = [
    {"tool": "weather_query", "result": "北京今天晴，25°C"}
]
```

### 8. ReplyDeliverStage (order=80)

**职责**：将回复发送回平台。

```python
# 输入
ctx.reply_content = ["让我查一下天气", "北京今天晴，25°C"]

# 输出
# 通过 adapter_bridge.send_message() 发送回复
```

## 插件扩展

### 注入自定义 Stage

插件可以通过 `PromptSectionProvider` 协议注入自定义 Stage：

```python
# plugins/my_plugin/plugin.py
from core.pipeline.stage import PipelineStage

class MyCustomStage(PipelineStage):
    def __init__(self):
        super().__init__(name="my_custom", order=35)
    
    async def process(self, ctx: PipelineContext) -> None:
        # 在 SessionInit 和 ContextBuild 之间执行
        ctx.user_input = f"[插件处理] {ctx.user_input}"

def load(manager):
    from core.pipeline.standard import standard_pipeline
    standard_pipeline.add_stage(MyCustomStage())
```

### Hook 现有 Stage

通过 EventBus 监听 Stage 的前后事件：

```python
from core.bus.bus import bus

@bus.on("pipeline_stage_before_llm_call")
def before_llm_call(ctx: PipelineContext):
    print(f"准备调用 LLM，上下文长度：{len(ctx.context_messages)}")

@bus.on("pipeline_stage_after_llm_call")
def after_llm_call(ctx: PipelineContext):
    print(f"LLM 响应：{ctx.llm_response[:100]}...")
```

## 错误处理

### Stage 级错误恢复

每个 Stage 可以实现 `on_error` 方法来处理错误：

```python
class ResilientStage(PipelineStage):
    async def process(self, ctx: PipelineContext) -> None:
        # 可能失败的操作
        result = await risky_operation()
        ctx.data = result
    
    async def on_error(self, ctx: PipelineContext, error: Exception) -> bool:
        if isinstance(error, TemporaryError):
            # 可恢复错误，设置默认值
            ctx.data = "default_value"
            return True  # 继续执行
        else:
            # 不可恢复错误
            return False  # 终止管道
```

### 提前终止

任何 Stage 都可以设置 `ctx.should_stop = True` 来提前终止管道：

```python
class PermissionCheckStage(PipelineStage):
    async def process(self, ctx: PipelineContext) -> None:
        if not self.has_permission(ctx.event.sender_id):
            ctx.should_stop = True
            ctx.reply_content = ["权限不足"]
```

设置 `should_stop` 后，后续普通 Stage 会被跳过，但 `always_run=True` 的 Stage 仍会执行。

## 性能监控

StandardPipeline 会自动记录每个 Stage 的执行时间：

```
[BuildUserInput] 完成 (1.2ms)
[NameMapping] 完成 (0.8ms)
[SessionInit] 完成 (5.3ms)
[ContextBuild] 完成 (2.1ms)
[LLMCall] 完成 (1250.5ms)
[MessageParse] 完成 (0.5ms)
[ToolExecute] 完成 (320.8ms)
[ReplyDeliver] 完成 (15.2ms)
```

## 测试

Pipeline 的模块化设计使得每个 Stage 都可以独立测试：

```python
import pytest
from core.pipeline.stages.name_mapping import NameMappingStage
from core.pipeline.context import PipelineContext

@pytest.mark.asyncio
async def test_name_mapping():
    stage = NameMappingStage()
    ctx = PipelineContext()
    ctx.user_input = "@Bot 你好"
    
    await stage.process(ctx)
    
    assert "@Bot" in ctx.mapped_names
    assert ctx.mapped_names["@Bot"] == "Tali"
```

完整测试示例见 `tests/unit/pipeline/`。

## 与旧架构的对比

### 旧架构（直接调用）

```python
# core/main.py (旧)
async def _handle_respond_message(self, event):
    user_input = event.message.text
    session = self.session_manager.get(event.sender_id)
    context = self.build_context(session, user_input)
    llm_response = await self.chat_llm.chat(context)
    parsed = parse_xml_msg(llm_response)
    if parsed.tool_calls:
        tool_results = await self.execute_tools(parsed.tool_calls)
    reply = self.build_reply(parsed, tool_results)
    await self.adapter_bridge.send_message(reply)
```

**问题**：
- 所有逻辑耦合在一个方法里
- 难以测试
- 插件无法介入中间步骤

### 新架构（Pipeline）

```python
# core/main.py (新)
async def _handle_respond_message(self, event):
    ctx = PipelineContext()
    ctx.event = event
    await self.pipeline.execute(ctx)
```

**优势**：
- 每个 Stage 独立封装
- 易于测试和维护
- 插件可以 hook 任意阶段

## 最佳实践

1. **单一职责** — 每个 Stage 只做一件事
2. **无副作用** — 除了修改 `ctx`，不要修改全局状态
3. **幂等性** — 尽量让 Stage 可以重复执行
4. **错误边界** — 实现 `on_error` 处理预期错误
5. **日志记录** — 记录关键决策点，方便调试

## 下一步

- [多智能体架构](multi-agent.md) — 了解 ChatLLM/PlanLLM/ToolLLM
- [事件系统](event-system.md) — 理解 EventBus 和插件 hook
- [插件开发](../development/plugin-development.md) — 开发自定义插件
