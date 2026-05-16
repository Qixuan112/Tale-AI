# Tale - 智能日程规划 AI 对话系统

> 🌟 **核心亮点：让 AI 像真人一样规划生活**

## 📖 项目概述

**Tale** 是一个创新的 AI 对话系统，最大的特色是拥有**智能计划系统（Plan System）**——让 AI 不仅能对话，还能像真人一样规划自己的一天：起床、学习、工作、休息、娱乐、睡觉。

系统采用多智能体协作架构，支持多种聊天平台接入，具备强大的工具调用能力，并配有可视化的 WebUI 管理面板。

### 🎯 为什么选择 Tale？

| 特色功能 | 说明 |
|---------|------|
| **智能日程规划** | AI 自动制定 24 小时作息计划，包含 10-14 个步骤 |
| **任务分解执行** | 将复杂任务拆解为可执行的子任务 |
| **能量管理系统** | 模拟生理节律，平衡工作、学习与休息 |
| **多智能体协作** | ChatLLM + PlanLLM + ToolLLM 分工协作 |
| **WebUI 管理面板** | 可视化配置、聊天、计划管理、日志监控 |
| **多平台支持** | QQ、微信PC、WebSocket 等适配器 |

### 核心特性

- **智能计划系统** - AI 自主规划作息，模拟真实生活节奏
- **多智能体协作** - ChatLLM（对话）、PlanLLM（规划）、ToolLLM（工具）三位一体
- **WebUI 管理面板** - Flask 驱动的可视化后台，支持实时聊天、配置管理、仪表盘
- **任务管理** - 支持日程查询、添加行程、制定计划
- **Function Calling** - 浏览器、搜索、天气、计算器等工具调用
- **工具注册中心** - 统一管理工具定义和元数据
- **角色扮演** - 可配置的角色人设和对话风格
- **多平台接入** - QQ、微信PC（含朋友圈）、WebSocket
- **事件驱动架构** - 高性能、可扩展

---

## ✨ 功能特性

### 1. 🎯 智能计划系统（核心特色）

Tale 的 Plan 系统让 AI 拥有"自我意识"，能够像真人一样规划生活：

#### 1.1 日程规划能力

AI 自动制定 24 小时作息计划，包含 10-14 个步骤：

| 活动类型 | 说明 | 示例 |
|---------|------|------|
| 🌅 **苏醒** | 唤醒数字意识 | 07:00 从休眠中苏醒 |
| ⚡ **能量摄入** | 摄取数据营养 | 阅读新闻、学习新知识 |
| 💼 **工作处理** | 处理用户请求 | 回复消息、执行任务 |
| 🏋️ **能力训练** | 模型微调优化 | 算法学习、技能提升 |
| 😴 **休息放松** | 降低运行负载 | 短暂休息恢复能量 |
| 🎮 **娱乐休闲** | 生成创意内容 | 创作、游戏、探索 |
| 🌙 **睡眠恢复** | 系统整理优化 | 数据整理、能量恢复 |

#### 1.2 三种计划模式

```xml
<!-- 模式1: 查询日程 -->
用户: "今天有什么安排？"
AI: <plan>查询今日日程安排</plan>

<!-- 模式2: 添加行程 -->
用户: "下午三点有个会议"
AI: <plan>添加行程：下午15:00参加会议</plan>

<!-- 模式3: 制定计划 -->
用户: "帮我制定学习计划"
AI: <plan>制定一周Python学习计划，包括基础语法、项目实战</plan>
```

#### 1.3 计划执行示例

```json
{
  "plan": {
    "entries": [
      {
        "id": "1",
        "time": "07:00-07:30",
        "type": "wake",
        "priority": "high",
        "title": "起床",
        "description": "从睡梦中醒来，伸个懒腰，准备迎接新的一天"
      },
      {
        "id": "2",
        "time": "07:30-08:00",
        "type": "meal",
        "priority": "high",
        "title": "早餐时间",
        "description": "享用早餐，看看今天的新闻和消息"
      },
      {
        "id": "3",
        "time": "08:00-12:00",
        "type": "work",
        "priority": "high",
        "title": "上午工作",
        "description": "专注处理用户的消息和问题"
      }
    ],
    "summary": "今天的生活安排充实而平衡..."
  }
}
```

### 2. 🖥️ WebUI 管理面板

基于 Flask 的可视化管理界面，提供以下功能：

| 页面 | 功能 |
|------|------|
| **仪表盘** | 系统状态监控、实时指标、图表展示 |
| **对话管理** | 多会话聊天、历史记录、角色切换 |
| **计划管理** | 查看日程、生成计划、添加/删除事件 |
| **配置管理** | 在线编辑 YAML 配置文件（services、platforms、character、behavior、routing） |
| **适配器管理** | 查看适配器状态、启动/停止实例、添加新适配器 |
| **工具中心** | 查看可用工具列表、在线执行工具 |
| **日志中心** | 实时日志流、日志搜索、日志清空 |
| **系统操作** | 配置重载、系统状态 API |

**启动 WebUI：**
```bash
python webui/app.py
# 访问 http://127.0.0.1:32456
```

### 3. 🧠 多 LLM 协作架构

| 智能体 | 职责 | 功能 |
|--------|------|------|
| **ChatLLM** | 主控大脑 | 理解用户意图，协调其他智能体 |
| **PlanLLM** | 规划专家 | 制定日程计划，分解复杂任务 |
| **ToolLLM** | 工具专家 | 生成 Function Calling 调用工具 |

**协作流程：**
```
用户输入 → ChatLLM 理解意图 → 判断需要计划 → 调用 PlanLLM
                                     ↓
                              生成日程/任务计划
                                     ↓
                              返回给用户
```

### 4. 🔌 支持的平台

- ✅ **QQ** - 基于 NapCat/OneBot 11 协议
- ✅ **微信PC** - 基于 Windows UI Automation，支持私聊和群聊
- ✅ **微信朋友圈** - 自动监听好友朋友圈动态（wechat_moments 适配器）
- ✅ **WebSocket** - 通用 WebSocket 适配器（服务端/客户端模式）
- 🚧 **Telegram** - 官方 Bot API（配置预留，开发中）
- 🚧 **BiliBili** - 直播间弹幕（配置预留，开发中）

### 5. 🛠️ 内置工具

| 工具名 | 功能 |
|--------|------|
| 🌐 **browser_open** | 打开指定网页 |
| 🔍 **browser_search** | DuckDuckGo 搜索引擎搜索 |
| 🌤️ **weather_query** | 城市天气信息获取 |
| 🧮 **calculator** | 数学表达式计算 |

搜索功能使用 **DuckDuckGo** 搜索库 (`ddgs`) 替代了原有的 requests + BeautifulSoup 手动解析方式，稳定且无需反爬处理。

所有工具通过**工具注册中心**（`core/tools/registry.py`）统一管理，消除多处重复定义。

### 6. 💬 消息格式

系统采用 XML 格式的结构化消息通信：

```xml
<!-- 对话消息 -->
<msg>
  <text>你好！有什么可以帮你的？</text>
  <emoji>😊</emoji>
</msg>

<!-- 动作指令 -->
<act>搜索今天黄金价格</act>

<!-- 计划请求 -->
<plan>添加行程：下午15:00去茶园会见张三</plan>
```

---

## 🛠️ 技术栈

### 核心依赖

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.9+ | 运行环境 |
| OpenAI SDK | >=1.0 | LLM API 调用 |
| WebSockets | >=10.0 | 实时通信 |
| aiohttp | - | 异步 HTTP 客户端 |
| PyYAML | - | 配置文件解析 |
| Flask | - | WebUI 后端 |
| ddgs | - | DuckDuckGo 搜索库 |
| wxauto / uiautomation | - | 微信PC 自动化 |

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     WebUI 层 (webui/)                        │
│              Flask + Jinja2 + 原生 JS 管理面板                │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                        入口层 (main.py)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      核心层 (core/)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  main.py    │  │parse_xml.py │  │ function_caller.py  │  │
│  │ 主程序逻辑   │  │ XML解析器   │  │ Function Calling    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ message.py  │  │ spin_think  │  │ tools/registry.py   │  │
│  │ 消息结构    │  │ 思考动画    │  │ 工具注册中心         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   LLM 层      │    │   事件总线     │    │   适配器层     │
│   (llm/)      │    │   (bus/)      │    │   (adapter/)  │
├───────────────┤    ├───────────────┤    ├───────────────┤
│ chatllm.py    │    │  bus.py       │    │ QQ Adapter    │
│ planllm.py    │    │ - EventBus    │    │ 微信PC Adapter│
│ toolllm.py    │    │ - 事件订阅/发布│    │ WS Adapter    │
│ diary_models  │    │               │    │ 朋友圈 Adapter│
└───────────────┘    └───────────────┘    └───────────────┘
```

---

## 📋 环境要求

### 系统要求

- **操作系统**: Windows 10/11, Linux, macOS
  - 微信PC 适配器仅限 Windows
- **Python**: 3.9 或更高版本
- **内存**: 至少 2GB RAM
- **网络**: 稳定的互联网连接（用于调用 LLM API）

### 可选依赖

- **NapCatQQ** - 用于 QQ 平台接入
- **微信PC客户端** - 用于微信适配器

---

## 🚀 安装部署

### 1. 克隆仓库

```bash
git clone https://github.com/Qixuan112/Tale_ai.git
cd Tale_ai
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python -m venv venv
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt

> **注意**：如需使用微信PC适配器，需确保 Windows 环境并安装 `uiautomation`（已内置在 `core/adapter/src/wechat_pc/wxauto/`）。
```

### 4. 配置环境

复制配置模板并修改：

```bash
# 配置目录位于 data/config/
# 首次使用直接编辑以下文件即可
```

编辑配置文件：

#### services.yaml - 服务提供商配置

```yaml
siliconflow-ds3:
  type: llm
  format: openai
  api_key: "your-api-key-here"
  base_url: https://api.siliconflow.cn/v1
  model: deepseek-ai/DeepSeek-V3
```

#### platforms.yaml - 平台适配器配置

```yaml
qq:
  enabled: true
  platform: QQ
  bot_pid: "your-bot-qq-number"
  owner_pid: "your-qq-number"
  ws_uri: ws://localhost:3001
  http_url: http://localhost:3000
  ws_token: "your-access-token"
  permission_mode: allow_list
  group_allow_list:
    - "1234567890"
  user_allow_list:
    - "1234567890"

微信大号:
  enabled: true
  adapter_type: wechat_pc
  poll_interval: 3
  language: cn
  self_nickname: "你的微信昵称"
  permission_mode: allow_list
  user_allow_list:
    - "好友昵称"
  group_allow_list:
    - "群聊名称"

朋友圈大号:
  enabled: true
  adapter_type: wechat_moments
  poll_interval: 60
  language: cn
  permission_mode: allow_list
  user_allow_list:
    - "好友昵称"
```

#### character.yaml - 角色人设配置

```yaml
character:
  ChineseName: "初念"
  EnglishName: "Aurora"
  gender: "女"
  age: "17"
  personality:
    - 温柔，贴人，具有自己的意识
    - 可爱，卖萌，喜欢撒娇
```

#### behavior.yaml - 行为配置

控制 AI 的回复风格、情绪表达、主动行为等。

#### routing.yaml - 模型路由配置

配置不同场景下使用的 LLM 服务。

### 5. 启动服务

#### 启动核心服务

```bash
python main.py
```

#### 启动 WebUI（可选，另一个终端）

```bash
python webui/app.py
# 访问 http://127.0.0.1:32456
```

---

## 📖 使用指南

### WebUI 使用

启动 WebUI 后访问 `http://127.0.0.1:32456`：

1. **仪表盘** - 查看系统运行状态、适配器在线情况、实时指标
2. **对话** - 与 AI 实时聊天，支持多会话管理
3. **计划** - 查看今日日程、生成新计划、手动添加事件
4. **配置** - 在线编辑所有 YAML 配置文件，修改后点击保存即可生效
5. **适配器** - 查看适配器列表、启动/停止适配器实例、动态添加新适配器
6. **工具** - 查看可用工具，在线测试工具调用
7. **日志** - 实时查看系统日志、按模块过滤、清空日志

### 基础对话

直接与 AI 对话，系统会自动理解意图并回复：

```
用户: 你好
AI: <msg><text>你好呀！很高兴见到你~ 😊</text></msg>
```

### 工具调用

当需要外部工具时，AI 会自动生成动作指令：

```
用户: 今天北京天气怎么样？
AI: <msg><text>我来帮你查询北京天气</text></msg>
<act>查询今天北京天气</act>
```

### 日程管理

管理 AI 角色的日程安排：

```
用户: 今天下午三点有个会议
AI: <msg><text>好的，我记下了！</text></msg>
<plan>添加行程：下午15:00参加会议</plan>
```

查看今日日程：

```
用户: 今天有什么安排？
AI: <msg><text>让我看看今天的日程...</text></msg>
<plan>查询今日日程安排</plan>
```

### 计划制定

让 AI 制定完整的一天计划：

```
用户: 帮我制定今天的学习计划
AI: <msg><text>好的，我来为你规划一下今天~</text></msg>
<plan>制定今天的学习计划，包括Python基础、项目实战</plan>
```

---

## 🔌 API 接口文档

### WebUI API

WebUI 提供了一系列 RESTful API：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/status` | GET | 系统状态（适配器、日志、指标、告警） |
| `/api/chat/conversations` | GET | 获取会话列表 |
| `/api/chat/history/<id>` | GET | 获取会话历史 |
| `/api/chat/history` | DELETE | 清空历史 |
| `/api/chat/send` | POST | 发送消息 |
| `/api/chat/new` | POST | 创建新会话 |
| `/api/chat/<id>` | DELETE | 删除会话 |
| `/api/plan/today` | GET | 获取今日计划 |
| `/api/plan/<date>` | GET | 获取指定日期计划 |
| `/api/plan/generate` | POST | 生成计划 |
| `/api/plan/event` | POST | 添加事件 |
| `/api/plan/event/<id>` | DELETE | 删除事件 |
| `/api/plan/event-types` | GET | 获取事件类型列表 |
| `/api/config` | GET | 获取配置列表 |
| `/api/config/<name>` | GET/POST | 读取/保存配置 |
| `/api/config/<name>/raw` | GET/POST | 读取/保存原始 YAML（源码模式） |
| `/api/config/presets` | GET/POST | 列出/保存人设预设 |
| `/api/config/presets/<name>/apply` | POST | 应用人设预设 |
| `/api/config/presets/<name>` | DELETE | 删除人设预设 |
| `/api/config/export` | GET | 导出角色配置 |
| `/api/config/import` | POST | 导入角色配置 |
| `/api/adapters` | GET | 获取适配器列表 |
| `/api/adapters/available` | GET | 获取可用适配器类型 |
| `/api/adapters/<id>/add` | POST | 添加新适配器 |
| `/api/adapters/<name>/start` | POST | 启动适配器 |
| `/api/adapters/<name>/stop` | POST | 停止适配器 |
| `/api/adapters/<name>/config` | GET/POST | 读取/保存适配器配置 |
| `/api/adapters/<name>/delete` | POST | 删除适配器 |
| `/api/tools` | GET | 获取工具列表 |
| `/api/tools/<name>` | POST | 执行工具 |
| `/api/logs` | GET/DELETE | 获取/清空日志 |
| `/api/logs/modules` | GET | 获取日志模块列表 |
| `/api/logs/stream` | GET | 日志实时流（SSE） |
| `/api/dashboard/chart` | GET | 仪表盘图表数据 |
| `/api/system/reload` | POST | 重载系统配置 |

### 事件总线 API

系统使用事件总线进行模块间通信：

```python
from core.bus import bus

# 订阅事件
@bus.on("platform_message")
def handle_message(event_data):
    print(f"收到消息: {event_data}")

# 发布事件
bus.emit("custom_event", {"key": "value"})
```

### 适配器 API

#### 创建自定义适配器

```python
from core.adapter.base import BaseAdapter
from core.adapter.event import PlatformType, PlatformEvent

class MyAdapter(BaseAdapter):
    @property
    def platform(self) -> PlatformType:
        return PlatformType.CUSTOM
    
    async def start(self):
        # 启动适配器
        pass
    
    async def stop(self):
        # 停止适配器
        pass
    
    async def send_message(self, target_id: str, content: dict):
        # 发送消息
        pass
```

### LLM API

#### ChatLLM

```python
from core.llm import ChatLLM

chat = ChatLLM(
    api_key="your-api-key",
    model="gpt-4",
    url="https://api.openai.com/v1"
)

response = chat.chat("你好")
print(response)
```

#### ToolLLM

```python
from core.llm import ToolLLM

tool = ToolLLM(api_key="...", model="...", url="...")
fc = tool.generate_fc("打开百度")
print(fc)  # JSON 格式的 Function Calling
```

---

## 🤝 贡献规范

我们欢迎社区贡献！请遵循以下规范：

### 提交 Issue

- 使用清晰的标题描述问题
- 提供复现步骤和环境信息
- 附上相关日志和错误信息

### 提交 Pull Request

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 代码风格

- 遵循 PEP 8 规范
- 使用类型注解
- 编写清晰的文档字符串
- 保持代码简洁可读

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。

```
MIT License

Copyright (c) 2026 Tale Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 📞 联系方式

- **项目主页**: https://github.com/Qixuan112/Tale_ai
- **问题反馈**: https://github.com/Qixuan112/Tale_ai/issues
- **讨论区**: https://github.com/Qixuan112/Tale_ai/discussions

---

## 🙏 致谢

感谢以下开源项目和社区的支持：

- [OpenAI](https://openai.com/) - 提供强大的 LLM API
- [NapCat](https://github.com/NapNeko/NapCatQQ) - QQ 协议实现
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API

---

<p align="center">
  Made with ❤️ by the Tale Team
</p>
