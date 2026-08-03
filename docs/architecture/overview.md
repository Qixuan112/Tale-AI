# 架构总览

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                          用户交互层                              │
│  QQ  │  WeChat  │  WebSocket  │  Console  │  WebUI (Flask)     │
└────────────────────┬────────────────────────────────────────────┘
                     │
            ┌────────▼────────┐
            │  Platform       │
            │  Adapters       │ ← 热插拔适配器
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  EventBus       │ ← 事件总线
            │  (Pub/Sub)      │
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │ Message         │ ← 权限/唤醒词检查
            │ Processor       │
            └────────┬────────┘
                     │
            ┌────────▼────────┐
            │  Pipeline       │ ← 消息处理管道
            │  (8 Stages)     │
            └─────┬───┬───┬───┘
                  │   │   │
        ┌─────────┘   │   └─────────┐
        │             │             │
   ┌────▼────┐   ┌───▼────┐   ┌───▼────┐
   │ ChatLLM │   │PlanLLM │   │ToolLLM │ ← 三智能体
   └────┬────┘   └───┬────┘   └───┬────┘
        │            │            │
   ┌────▼────────────▼────────────▼────┐
   │      Tool System / Plugin System  │ ← 工具调用 & 插件
   └────────────────┬──────────────────┘
                    │
            ┌───────▼────────┐
            │  Data Layer    │
            │  (YAML/JSON)   │
            └────────────────┘
         Config / Plans / Sessions
```

## 核心组件

### 1. 适配器层（Adapters）

**职责**：连接不同平台，将平台消息转换为统一的 `PlatformEvent`。

**支持平台**：
- **QQ** — NapCat/OneBot 11 协议（WebSocket）
- **WeChat PC** — Windows UIA 自动化
- **WebSocket** — 自定义协议
- **Console** — 命令行交互

**核心类**：
- `BaseAdapter` ([core/adapter/base.py](../../core/adapter/base.py)) — 适配器抽象基类
- `PlatformEvent` ([core/adapter/event.py](../../core/adapter/event.py)) — 统一事件格式
- `AdapterManager` ([core/adapter/manager.py](../../core/adapter/manager.py)) — 适配器生命周期管理

**特点**：
- 热插拔（运行时启动/停止）
- 统一事件格式
- 独立配置（`platforms.yaml`）

详见 [适配器架构](adapters.md)。

---

### 2. 事件总线（EventBus）

**职责**：进程内发布/订阅系统，解耦各组件。

**核心类**：
- `EventBus` ([core/bus/bus.py](../../core/bus/bus.py)) — 单例事件总线

**主要事件**：
```python
# 平台消息
bus.emit("platform_message", event)

# 管道阶段
bus.emit("pipeline_stage_before_llm_call", ctx)
bus.emit("pipeline_stage_after_llm_call", ctx)

# 配置变更
bus.emit("config_reloaded", config_type)
```

**特性**：
- 支持同步/异步监听器
- 优先级排序
- 一次性监听（`once`/`aonce`）

详见 [事件系统](event-system.md)。

---

### 3. 消息处理器（MessageProcessor）

**职责**：权限检查、唤醒词检测、路由决策。

**核心类**：
- `MessageProcessor` ([core/adapter/message_processor.py](../../core/adapter/message_processor.py))

**处理流程**：
```
平台消息 → 黑白名单检查 → 唤醒词检测 → 路由决策
                                            ↓
                            RESPOND / SILENT / IGNORE
```

**路由类型**：
- `RESPOND` — 响应消息（进入 Pipeline）
- `SILENT` — 静默记录（不回复，但记录上下文）
- `IGNORE` — 完全忽略

---

### 4. Pipeline 系统

**职责**：标准化消息处理流程，模块化各处理阶段。

**8 个标准 Stage**：
1. **BuildUserInput** (order=10) — 提取用户输入
2. **NameMapping** (order=20) — @mention 名称映射
3. **SessionInit** (order=30) — 会话初始化
4. **ContextBuild** (order=40) — 构建 LLM 上下文
5. **LLMCall** (order=50) — 调用 ChatLLM
6. **MessageParse** (order=60) — 解析 XML 标签
7. **ToolExecute** (order=70) — 执行工具调用
8. **ReplyDeliver** (order=80) — 发送回复

**核心类**：
- `PipelineContext` ([core/pipeline/context.py](../../core/pipeline/context.py)) — 管道上下文
- `PipelineStage` ([core/pipeline/stage.py](../../core/pipeline/stage.py)) — 阶段抽象
- `StandardPipeline` ([core/pipeline/standard.py](../../core/pipeline/standard.py)) — 标准管道实现

**特性**：
- 责任链模式
- 错误恢复机制
- 插件 hook 点
- 性能监控

详见 [Pipeline 系统](pipeline.md)。

---

### 5. 多智能体系统

**职责**：三个专职 LLM 智能体协作完成任务。

#### ChatLLM

**职责**：主对话智能体，处理用户交互。

**输出格式**：
```xml
<msg>我来帮你查一下天气</msg>
<tool>weather_query</tool>
<act>思考片刻</act>
```

**核心类**：
- `ChatLLM` ([core/llm/chatllm.py](../../core/llm/chatllm.py))

#### PlanLLM

**职责**：生成 24 小时日程计划。

**计划类型**：
- wake（起床）
- meal（用餐）
- work（工作）
- study（学习）
- rest（休息）
- social（社交）
- entertainment（娱乐）
- exercise（运动）
- sleep（睡觉）

**核心类**：
- `PlanLLM` ([core/llm/planllm.py](../../core/llm/planllm.py))
- `DailyPlan` ([core/llm/diary_models.py](../../core/llm/diary_models.py))

#### ToolLLM

**职责**：执行工具调用（OpenAI Function Calling）。

**内置工具**：
- `browser_open` — 打开网页
- `browser_search` — DuckDuckGo 搜索
- `weather_query` — 天气查询
- `calculator` — 计算器

**核心类**：
- `ToolLLM` ([core/llm/toolllm.py](../../core/llm/toolllm.py))
- `ToolRegistry` ([core/tools/registry.py](../../core/tools/registry.py))

详见 [多智能体架构](multi-agent.md)。

---

### 6. 插件系统

**职责**：扩展系统功能，无需修改核心代码。

**6 个扩展点**：
1. **ToolProvider** — 注册自定义工具
2. **EventSubscriber** — 订阅 EventBus 事件
3. **WebUIProvider** — 添加 WebUI 页面/API
4. **XMLTagHandler** — 处理自定义 XML 标签
5. **PromptSectionProvider** — 注入 Prompt 片段
6. **PipelineStageProvider** — 注入自定义 Pipeline Stage

**插件结构**：
```
plugins/my_plugin/
├── manifest.json    # 元数据 + 扩展点声明
└── plugin.py        # 实现代码
```

**核心类**：
- `PluginManager` ([core/plugin/manager.py](../../core/plugin/manager.py))

详见 [插件开发指南](../development/plugin-development.md)。

---

### 7. 上下文管理（Context）

**职责**：模块化 Prompt 构建，支持 Anthropic 风格的 Prompt Caching。

**核心类**：
- `AgentContext` ([core/llm/context/agent_context.py](../../core/llm/context/agent_context.py)) — 上下文管理器
- `PromptSection` ([core/llm/context/section.py](../../core/llm/context/section.py)) — Prompt 片段
- `ContextConfig` ([core/llm/context/config.py](../../core/llm/context/config.py)) — 缓存策略配置

**缓存策略**：
```yaml
# data/config/context.yaml
chat:
  cache_strategy: aggressive  # aggressive / moderate / disabled
  cacheable_sections:
    - system_base
    - character_profile
    - tool_definitions
```

**工作流程**：
1. 注册多个 `PromptSection`
2. 按 `order` 排序
3. 可缓存部分放前面
4. 组装为最终 Prompt

---

### 8. 配置系统

**职责**：YAML 配置文件管理，支持热重载。

**配置文件**：
- `services.yaml` — LLM API 配置
- `platforms.yaml` — 适配器配置
- `character.yaml` — 角色设定
- `behavior.yaml` — 行为配置
- `routing.yaml` — 模型路由
- `context.yaml` — 上下文缓存策略（可选）

**核心类**：
- `ConfigLoader` ([core/config/provide.py](../../core/config/provide.py))

**热重载**：
```python
from core.config.provide import config_loader

# 重新加载配置
config_loader.reload()

# 发送重载事件
bus.emit("config_reloaded", "services")
```

---

### 9. WebUI 管理面板

**职责**：Web 界面管理、配置编辑、实时监控。

**主要页面**：
- **Dashboard** — 系统状态总览
- **Chat** — 聊天测试
- **Plan** — 日程查看
- **Config** — 配置编辑器
- **Adapters** — 适配器管理
- **Tools** — 工具中心
- **Logs** — 日志查看器

**技术栈**：
- Flask（后端）
- Vanilla JS（前端）
- WebSocket（实时通信）

**认证**：
- 默认启用（首次运行生成 token）
- Token 存储在 `data/config/webui_token`
- 可在 `webui/app.py` 中关闭

**引导系统**：
- Galgame 风格新手引导
- 角色对话式配置流程
- 角落悬浮 mascot

---

## 数据流示例

### 完整消息流

```
1. 用户在 QQ 发送: "@Bot 今天天气怎么样？"
          ↓
2. QQ Adapter 接收 OneBot 事件
          ↓
3. 转换为 PlatformEvent
          ↓
4. 发送到 EventBus: "platform_message"
          ↓
5. MessageProcessor 检查权限 + 唤醒词 → RESPOND
          ↓
6. 进入 StandardPipeline
   ├─ BuildUserInput: 提取 "今天天气怎么样？"
   ├─ NameMapping: "@Bot" → "Tali"
   ├─ SessionInit: 加载会话历史
   ├─ ContextBuild: 构建 LLM 上下文
   ├─ LLMCall: ChatLLM 返回 "<msg>让我查一下</msg><tool>weather_query</tool>"
   ├─ MessageParse: 解析 XML
   ├─ ToolExecute: ToolLLM 调用天气工具 → "北京今天晴，25°C"
   └─ ReplyDeliver: 发送 "让我查一下\n北京今天晴，25°C"
          ↓
7. Adapter 将回复发送到 QQ
```

---

## 目录结构

```
Tale-AI/
├── main.py                     # 入口文件
├── core/                       # 核心代码
│   ├── main.py                 # TaleCore 主控制器
│   ├── adapter/                # 适配器
│   │   ├── base.py
│   │   ├── manager.py
│   │   ├── event.py
│   │   ├── integration.py      # AdapterEventBridge
│   │   ├── message_processor.py
│   │   └── src/                # 平台适配器实现
│   │       ├── qq/
│   │       ├── wechat_pc/
│   │       └── websocket/
│   ├── bus/                    # 事件总线
│   │   └── bus.py
│   ├── pipeline/               # Pipeline 系统
│   │   ├── base.py
│   │   ├── standard.py
│   │   ├── context.py
│   │   ├── stage.py
│   │   └── stages/             # 标准 Stage 实现
│   ├── llm/                    # 多智能体
│   │   ├── chatllm.py
│   │   ├── planllm.py
│   │   ├── toolllm.py
│   │   ├── diary_models.py
│   │   └── context/            # 上下文管理
│   ├── tools/                  # 工具系统
│   │   ├── registry.py
│   │   └── implementations/
│   ├── plugin/                 # 插件系统
│   │   ├── manager.py
│   │   └── protocols.py
│   ├── config/                 # 配置管理
│   │   ├── provide.py
│   │   └── prompt.py
│   └── parse_xml.py            # XML 解析器
├── webui/                      # WebUI
│   ├── app.py
│   ├── templates/
│   └── static/
├── plugins/                    # 插件目录
│   └── echo_tool/
├── data/                       # 数据目录（运行时生成）
│   ├── config/
│   ├── plans/
│   ├── sessions/
│   └── logs/
├── tests/                      # 测试
│   └── unit/
│       └── pipeline/
└── docs/                       # 文档
```

---

## 技术选型

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.8+ |
| LLM 调用 | OpenAI SDK（兼容格式） |
| Web 框架 | Flask |
| 配置格式 | YAML |
| 数据持久化 | JSON 文件 |
| QQ 协议 | OneBot 11 (WebSocket) |
| WeChat 自动化 | UIAutomation (Windows) |
| 搜索引擎 | DuckDuckGo |
| HTML 解析 | BeautifulSoup4 |

---

## 设计原则

1. **模块化** — 每个组件职责单一，低耦合
2. **可扩展** — 插件系统支持自定义扩展
3. **事件驱动** — EventBus 解耦组件通信
4. **配置化** — 所有行为通过 YAML 配置
5. **热插拔** — 适配器/插件运行时加载
6. **测试友好** — Pipeline Stage 独立测试

---

## 下一步

- [Pipeline 系统](pipeline.md) — 了解消息处理流程
- [多智能体架构](multi-agent.md) — 理解三智能体协作
- [事件系统](event-system.md) — 掌握 EventBus 使用
- [适配器架构](adapters.md) — 接入新平台
- [插件开发](../development/plugin-development.md) — 开发自定义功能
