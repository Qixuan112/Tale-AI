# 多智能体架构

## 概述

Tale-AI 采用**多智能体协作**架构，将不同职责分配给三个专职 LLM 智能体。每个智能体专注于特定任务，通过统一的上下文管理系统高效协作。

## 设计理念

### 为什么需要多智能体？

传统单一 LLM 架构的问题：
- **职责混乱** — 对话、规划、工具调用混在一起
- **Prompt 冲突** — 不同任务的指令互相干扰
- **性能浪费** — 简单任务也要调用大模型

多智能体优势：
- **职责清晰** — 每个智能体专注单一领域
- **独立优化** — 针对不同任务使用不同模型和 Prompt
- **并行执行** — 工具调用与对话生成可并行
- **成本优化** — 简单任务使用小模型

### 三智能体分工

```
┌──────────────────────────────────────────────────────┐
│                     用户输入                          │
└────────────────────┬─────────────────────────────────┘
                     │
            ┌────────▼────────┐
            │    ChatLLM      │ ← 主对话智能体
            │  (对话 + 决策)   │    生成回复 + XML 标签
            └────┬────┬───┬───┘
                 │    │   │
       ┌─────────┘    │   └──────────┐
       │              │              │
   ┌───▼────┐    ┌───▼────┐    ┌───▼────┐
   │  <msg> │    │ <tool> │    │ <plan> │
   │  回复   │    │ 工具   │    │ 规划   │
   └────────┘    └───┬────┘    └───┬────┘
                     │             │
                ┌────▼────┐   ┌───▼────┐
                │ToolLLM  │   │PlanLLM │ ← 专职智能体
                │Function │   │日程管理 │
                │ Calling │   │        │
                └─────────┘   └────────┘
```

---

## ChatLLM — 主对话智能体

### 职责

- 理解用户意图
- 生成自然语言回复
- 决策是否调用工具或规划
- 管理会话上下文

### 输出格式

ChatLLM 使用 **XML 标签** 来标记不同类型的输出：

```xml
<msg>让我帮你查一下今天的天气</msg>
<tool>weather_query</tool>
<act>思考片刻，打开浏览器</act>
```

**标签说明**：

| 标签 | 用途 | 处理方式 |
|------|------|----------|
| `<msg>` | 回复文本 | 直接发送给用户 |
| `<tool>` | 工具调用 | 交给 ToolLLM 执行 |
| `<plan>` | 日程请求 | 交给 PlanLLM 处理 |
| `<act>` | 动作描述 | 可选的角色扮演动作 |

### 核心实现

```python
from core.llm.chatllm import ChatLLM

# 初始化
chat_llm = ChatLLM(
    api_key="your-api-key",
    model="claude-3-5-sonnet-20241022",
    url="https://api.anthropic.com/v1",
    max_context=20  # 最大上下文轮数
)

# 发送消息
response = chat_llm.chat("今天天气怎么样？")
# 返回: "<msg>让我查一下</msg><tool>weather_query</tool>"
```

### 会话管理

ChatLLM 支持两种会话模式：

#### 1. 有状态模式（默认）

```python
# 自动管理历史
chat_llm.chat("你好")
chat_llm.chat("我刚才说了什么？")  # 能记住上一轮

# 清空历史
chat_llm.clear_history()
```

#### 2. 无状态模式（推荐）

```python
# 传入独立的消息列表
messages = [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
]

response = chat_llm.chat(
    user_input="我刚才说了什么？",
    messages=messages,  # 外部管理历史
    save_to_session=False  # 不持久化
)
```

### 上下文修剪

自动修剪机制保持上下文在限制内：

```python
# 配置
chat_llm.max_context = 20  # 最多 20 条消息

# 修剪规则
# 1. 始终保留所有 system 消息
# 2. 从最早的 user-assistant 对话对开始删除
# 3. 删除时成对删除（保持对话完整性）
```

---

## PlanLLM — 日程规划智能体

### 职责

- 生成每日作息计划
- 管理今日日程（增删改查）
- 处理时间冲突
- 维护长期目标

### 核心概念

#### 1. 日程条目（DiaryEntry）

```python
from core.llm.diary_models import DiaryEntry, EventType, Priority
from datetime import time

entry = DiaryEntry(
    id="abc123",
    title="团队周会",
    description="讨论本周进度",
    event_type=EventType.WORK,
    priority=Priority.HIGH,
    start_time=time(14, 0),   # 14:00
    end_time=time(15, 0),     # 15:00
    related_people=["张三", "李四"],
    location="会议室A"
)
```

**事件类型**：
- `wake` — 起床
- `meal` — 用餐
- `work` — 工作
- `study` — 学习
- `social` — 社交
- `entertainment` — 娱乐
- `rest` — 休息
- `exercise` — 运动
- `sleep` — 睡觉
- `appointment` — 约会
- `task` — 任务
- `other` — 其他

#### 2. 每日计划（DailyPlan）

```python
from core.llm.diary_models import DailyPlan
from datetime import date

plan = DailyPlan(date=date.today())

# 添加条目
success = plan.add_entry(entry)  # 自动检测冲突

# 查询即将到来的事件
upcoming = plan.get_upcoming_entries(current_time)

# 查找可用时间段
slot = plan.find_slot(duration_minutes=60, after_time=time(9, 0))
```

### 使用示例

#### 生成今日计划

```python
from core.llm.planllm import get_planllm

planllm = get_planllm()

# 生成完整作息计划
plan_text = planllm.generate_daily_plan("为我制定今天的学习计划")
```

LLM 生成的计划文本会被自动解析为结构化条目：

```
07:00-07:30  起床洗漱
07:30-08:00  早餐
08:00-09:00  晨读英语
09:00-12:00  Python 编程学习
...
```

#### 添加临时行程

```python
# 自然语言添加
result = planllm.add_event_from_request("今天下午3点开会")
# 返回: "已添加行程：团队会议\n时间：15:00-16:00"

# 冲突自动处理
result = planllm.add_event_from_request("下午3点约李四喝咖啡")
# 返回: "已添加行程：喝咖啡\n时间调整为 16:00（原时间冲突）"
```

#### 查询今日日程

```python
schedule = planllm.get_today_plan_display()
print(schedule)
```

输出：
```
今日日程（2026-08-03）

[高优先级] 团队周会 [14:00-15:00]
   类型：工作 | 地点：会议室A
   相关人员：张三, 李四

[中优先级] Python 学习 [16:00-18:00]
   类型：学习

[已过期] 晨读英语 [08:00-09:00]
```

### 长期目标管理

```python
# 添加目标
goal = planllm.add_goal(
    title="学会 Python",
    description="系统学习 Python 编程",
    category="study",
    priority="high",
    target_date="2026-12-31"
)

# 同步目标到今日日程
success = planllm.sync_goal_to_diary(goal.id)
# 自动生成今日子任务并插入日程
```

### 跨天清理

PlanLLM 自动检测新的一天：

```python
# 午夜 00:00 后首次调用
planllm.ensure_today_plan()

# 行为：
# 1. 保存昨日计划到 data/diary/plan_2026-08-02.json
# 2. 加载或生成今日计划
# 3. 清理已过期的条目
```

---

## ToolLLM — 工具调用智能体

### 职责

- 将动作指令转换为 Function Calling JSON
- 理解工具的使用场景
- 选择合适的工具和参数

### Function Calling 流程

```
ChatLLM: <tool>搜索今天黄金价格</tool>
    ↓
ToolLLM: 分析动作 → 生成 JSON
    ↓
{
  "name": "browser_search",
  "parameters": {
    "query": "今天黄金价格",
    "max_results": 5
  }
}
    ↓
FunctionCaller: 执行工具 → 返回结果
```

### 使用示例

```python
from core.llm.toolllm import get_toolllm

toolllm = get_toolllm()

# 生成 Function Calling JSON
fc_json = toolllm.generate_fc("搜索今天的天气")

# 返回
{
  "name": "weather_query",
  "parameters": {
    "location": "当前位置",
    "date": "today"
  }
}
```

### 内置工具

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `browser_search` | DuckDuckGo 搜索 | `query`, `max_results` |
| `browser_open` | 打开网页 | `url` |
| `weather_query` | 天气查询 | `location`, `date` |
| `calculator` | 数学计算 | `expression` |

### 查询可用工具

```python
# 获取工具列表（用于 ChatLLM Prompt）
tools_text = toolllm.query_tools()

# 返回 <chatllm> 格式的工具列表
"""
<chatllm>
可用工具列表：
1. browser_search - 搜索引擎查询
   参数：query (搜索关键词), max_results (结果数量)
2. weather_query - 天气查询
   参数：location (地点), date (日期)
...
</chatllm>
"""
```

---

## 上下文管理系统

### AgentContext — 模块化 Prompt

每个智能体使用 `AgentContext` 管理 Prompt 片段（Section）：

```python
from core.llm.context import AgentContext, PromptSection

context = AgentContext(agent_name="chat")

# 添加 Section
context.add_section(PromptSection(
    name="system_base",
    content="你是 Tali，一个友好的 AI 助手。",
    cacheable=True,    # 可缓存
    order=10           # 排序（越小越靠前）
))

context.add_section(PromptSection(
    name="tool_definitions",
    content="可用工具：browser_search, weather_query",
    cacheable=True,
    order=20
))

context.add_section(PromptSection(
    name="current_time",
    content=lambda: f"当前时间：{datetime.now()}",
    cacheable=False,   # 动态内容不可缓存
    order=100
))
```

### Prompt 缓存策略

支持 Anthropic 风格的 Prompt Caching：

#### 1. 单消息模式（默认）

```python
messages = context.build_messages_head("single_message")

# 返回
[
  {
    "role": "system",
    "content": "system_base + tool_definitions + current_time"
  }
]
```

#### 2. 多消息模式（推荐）

```python
messages = context.build_messages_head("multi_message")

# 返回
[
  {
    "role": "system",
    "content": "system_base + tool_definitions"  # 静态，可缓存
  },
  {
    "role": "system",
    "content": "current_time"  # 动态，不缓存
  }
]
```

**优势**：
- 第一条 system 消息字节稳定，命中 Prompt Cache
- 动态内容（时间、日程）单独在第二条 system 消息中
- 大幅降低 API 成本（cache read 便宜 10 倍）

### 动态内容注入

使用 `dynamic=True` 标记的 Section 会被注入到用户消息中：

```python
context.add_section(PromptSection(
    name="current_time",
    content="[当前时间] 2026-08-03 14:30",
    cacheable=False,
    dynamic=True,      # 注入到用户消息
    persist=False      # 不持久化到会话历史
))

# 获取动态提醒
reminder = context.get_dynamic_reminder()
# 返回: "<system_reminder>\n[当前时间] 2026-08-03 14:30\n</system_reminder>"

# 拼接到用户输入
user_input = f"{reminder}\n\n{original_input}"
```

### 配置文件

通过 `data/config/context.yaml` 配置缓存策略：

```yaml
# 全局默认
default_cache_strategy: multi_message

# 每个智能体独立配置
agents:
  chat:
    cache_strategy: multi_message
    cacheable_sections:
      - system_base
      - character_profile
      - tool_definitions
      - dialogue_examples
    non_cacheable_sections:
      - current_time
      - today_plan
  
  plan:
    cache_strategy: single_message
  
  tool:
    cache_strategy: multi_message
    cacheable_sections:
      - tool_definitions
      - fc_format_template
```

---

## 工厂函数

使用工厂函数获取预配置的智能体实例：

```python
# ChatLLM
from core.llm.context.factory import create_chat_context

context = create_chat_context(
    character_prompt="你是 Tali",
    dialogue_examples="用户：你好\nTali：你好！",
    persona_additional_prompt=""
)
chat_llm = ChatLLM(context=context)

# PlanLLM
from core.llm.context.factory import create_plan_context

context = create_plan_context(
    name="Tali",
    english_name="Tali",
    age="3岁",
    gender="女",
    values=["友好", "高效", "可靠"]
)
plan_llm = PlanLLM(context=context)

# ToolLLM
from core.llm.context.factory import create_tool_context

context = create_tool_context(
    tools_text="可用工具：browser_search, weather_query"
)
tool_llm = ToolLLM(context=context)
```

---

## 热重载

所有智能体监听 `config_reloaded` 事件自动更新：

```python
from core.bus import bus
from core.config.provide import config_loader

# 重新加载配置
config_loader.reload()
bus.emit("config_reloaded", "services")

# ChatLLM、PlanLLM、ToolLLM 自动：
# 1. 重新读取 API 配置
# 2. 重建 OpenAI 客户端
# 3. 刷新角色 Prompt（仅 ChatLLM/PlanLLM）
```

**注意**：
- PlanLLM 完全支持热重载
- ChatLLM/ToolLLM 仅热重载 API 配置，角色设定变更需重启

---

## 三智能体协作示例

### 完整流程

```python
# 1. 用户输入
user_input = "帮我搜索一下今天天气，然后把下午的会议改到明天"

# 2. ChatLLM 分析意图
response = chat_llm.chat(user_input)
# 返回: "<msg>好的，让我先查天气</msg><tool>weather_query</tool><plan>修改会议时间</plan>"

# 3. 解析 XML
from core.parse_xml import parse_xml_msg

parsed = parse_xml_msg(response)
# parsed.text_parts = ["好的，让我先查天气"]
# parsed.tool_calls = ["weather_query"]
# parsed.plan_requests = ["修改会议时间"]

# 4. ToolLLM 执行工具
if parsed.tool_calls:
    for action in parsed.tool_calls:
        fc_json = tool_llm.generate_fc(action)
        # 调用实际工具...

# 5. PlanLLM 处理日程
if parsed.plan_requests:
    for request in parsed.plan_requests:
        result = plan_llm.generate(request)

# 6. 组合回复
final_reply = "\n".join([
    parsed.text_parts[0],
    tool_results,
    plan_results
])
```

---

## 最佳实践

### 1. 模型选择

| 智能体 | 推荐模型 | 理由 |
|--------|----------|------|
| ChatLLM | Claude 3.5 Sonnet / GPT-4 | 需要强对话能力和 XML 生成 |
| PlanLLM | Claude 3 Haiku / GPT-3.5 | 结构化生成，小模型足够 |
| ToolLLM | Claude 3 Haiku / GPT-3.5 | Function Calling 简单 |

### 2. 上下文管理

- **启用 Prompt Caching** — 使用 `multi_message` 策略
- **分离动态内容** — 时间、日程等标记为 `dynamic=True`
- **控制历史长度** — ChatLLM 设置 `max_context=20`

### 3. 会话持久化

```python
from core.session import SessionManager

session_mgr = SessionManager()

# 绑定会话
chat_llm.set_session(sid="user_123", load_history=True)

# 自动持久化
chat_llm.chat(
    user_input="你好",
    persist_content="你好",  # 纯净原文
    save_to_session=True
)
```

### 4. 错误处理

```python
try:
    response = chat_llm.chat("你好")
except RuntimeError as e:
    if "provider 未初始化" in str(e):
        # API 配置缺失
        pass
    elif "API 返回空响应" in str(e):
        # API 调用失败
        pass
```

---

## 与 Pipeline 集成

多智能体系统通过 Pipeline Stage 调用：

```python
# LLMCallStage (order=50)
class LLMCallStage(PipelineStage):
    async def process(self, ctx: PipelineContext):
        chat_llm = get_chatllm()
        ctx.llm_response = chat_llm.chat(ctx.user_input)

# MessageParseStage (order=60)
class MessageParseStage(PipelineStage):
    async def process(self, ctx: PipelineContext):
        ctx.parsed_msg = parse_xml_msg(ctx.llm_response)

# ToolExecuteStage (order=70)
class ToolExecuteStage(PipelineStage):
    async def process(self, ctx: PipelineContext):
        if ctx.parsed_msg.tool_calls:
            tool_llm = get_toolllm()
            for action in ctx.parsed_msg.tool_calls:
                fc_json = tool_llm.generate_fc(action)
                # 执行工具...
```

详见 [Pipeline 系统](pipeline.md)。

---

## 性能指标

### 响应时间

| 操作 | 典型耗时 |
|------|----------|
| ChatLLM 单轮对话（无缓存） | 1-3 秒 |
| ChatLLM 单轮对话（有缓存） | 0.5-1 秒 |
| ToolLLM Function Calling | 0.3-0.8 秒 |
| PlanLLM 生成日程 | 2-5 秒 |
| PlanLLM 查询日程 | <10 毫秒（无 LLM 调用） |

### 成本优化

使用 Prompt Caching 的成本对比（Anthropic 定价）：

| 场景 | Cache Miss | Cache Hit | 节省 |
|------|------------|-----------|------|
| ChatLLM (10K tokens prompt) | $0.03 | $0.003 | **90%** |
| 每天 1000 次对话 | $30 | $3 | **$27/天** |

---

## 下一步

- [事件系统](event-system.md) — 智能体间通信机制
- [Pipeline 系统](pipeline.md) — 消息处理流程
- [插件开发](../development/plugin-development.md) — 扩展智能体能力
