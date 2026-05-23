<p align="center">
  <h1>Tale</h1>
  <p><strong>让 AI 像真人一样规划生活</strong> &nbsp;|&nbsp; <em>AI That Lives a Life of Its Own</em></p>
</p>

---

**Tale** 是一个多智能体 AI 对话系统。它不仅会聊天，还拥有**自主日程规划**能力——AI 角色会像真人一样安排自己的一天：起床、工作、休息、娱乐、睡觉。支持接入 QQ、微信、WebSocket 等平台，配有多功能 WebUI 管理面板。

**Tale** is a multi-agent AI conversation system with autonomous daily planning. The AI character schedules its own day — waking up, working, resting, playing — like a real person. Multi-platform support and a full-featured WebUI dashboard included.

---

## 亮点 / Highlights

| | |
|---|---|
| 🧠 **多智能体协作** | ChatLLM (对话) + PlanLLM (规划) + ToolLLM (工具) 三位一体 |
| 📅 **自主日程规划** | AI 自动制定 24 小时作息计划，模拟真实生活节奏 |
| 🛠️ **工具调用** | 浏览器、搜索、天气、计算器，支持插件扩展 |
| 🖥️ **WebUI 面板** | 可视化仪表盘、实时聊天、配置编辑、日志监控 |
| 🔌 **多平台接入** | QQ · 微信PC (含朋友圈) · WebSocket，适配器热插拔 |
| 🧩 **插件系统** | 6 种扩展点，manifest.json 自动发现，一键加载 |

---

## 快速开始 / Quick Start

```bash
git clone https://github.com/Qixuan112/Tale_ai.git
cd Tale_ai
pip install -r requirements.txt
python main.py              # 启动核心服务 + WebUI → http://127.0.0.1:32456
```

首次运行自动创建 `data/config/` 配置文件，编辑 `services.yaml` 填入 API Key 即可开始对话。

> 🔒 **安全提示**：WebUI 默认仅监听 `127.0.0.1`。如需远程访问，务必在反向代理后添加认证层，切勿直接暴露公网。  
> 🔒 **Security**: WebUI binds to localhost by default. Always add authentication behind a reverse proxy before exposing it.

---

## 架构 / Architecture

```
用户输入 → ChatLLM (意图理解) → PlanLLM (规划) / ToolLLM (工具)
                ↕
         事件总线 (EventBus) ← 插件系统 (Plugin) ← 适配器 (QQ/微信/WS)
                ↕
           WebUI (Flask) → 仪表盘 · 聊天 · 配置 · 日志
```

---

## 许可证 / License

**[GNU AGPL v3](LICENSE)** — 自由使用、修改、分发。对外提供服务须公开修改后的源代码。

---

<p align="center">
  <a href="https://github.com/Qixuan112/Tale_ai">GitHub</a> ·
  <a href="https://github.com/Qixuan112/Tale_ai/issues">Issues</a>
</p>
