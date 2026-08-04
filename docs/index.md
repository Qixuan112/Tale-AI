# Tale-AI 文档

<div align="center">
  <h2>AI That Lives a Life of Its Own</h2>
  <p><em>让 AI 像真人一样自主规划生活</em></p>
</div>

---

## 什么是 Tale-AI？

**Tale-AI** 是一个多智能体 AI 对话系统，具备自主日程规划能力。AI 角色会像真人一样安排自己的一天——起床、工作、休息、娱乐、睡觉，完全自主决策。

## 核心特性

### 多智能体架构
- **ChatLLM** — 主对话智能体，处理用户交互
- **PlanLLM** — 规划智能体，生成 24 小时日程安排
- **ToolLLM** — 工具调用智能体，执行浏览器、搜索、天气等功能

### Pipeline 消息处理系统
标准化的消息处理管道，包含 8 个处理阶段：

1. **BuildUserInput** — 构建用户输入
2. **NameMapping** — 名称映射
3. **SessionInit** — 会话初始化
4. **ContextBuild** — 上下文构建
5. **LLMCall** — LLM 调用
6. **MessageParse** — 消息解析
7. **ToolExecute** — 工具执行
8. **ReplyDeliver** — 回复发送

### 多平台支持
- QQ（NapCat/OneBot 11）
- WeChat PC（Windows UIA 自动化）
- WebSocket（自定义协议）
- 热插拔适配器架构

### 插件系统
6 个扩展点，支持：
- 自定义工具
- 事件订阅
- WebUI 扩展
- 自定义 XML 标签处理
- Prompt 注入

### WebUI 管理面板
- 实时聊天测试
- 配置文件编辑
- 日程计划查看
- 适配器管理
- 日志查看器

---

## 快速开始

```bash
git clone https://github.com/Qixuan112/Tale-AI.git
cd Tale-AI
pip install -r requirements.txt
python main.py
```

首次运行会自动创建配置文件在 `data/config/`。编辑 `services.yaml` 填入 API 密钥后即可开始使用。

WebUI 地址：[http://127.0.0.1:32456](http://127.0.0.1:32456)

详细步骤请参考 [安装部署指南](getting-started/installation.md)。

---

## 架构概览

```
用户输入 → Adapter → EventBus → MessageProcessor
                                      ↓
                                  Pipeline
                                      ↓
                     ┌────────────────┼────────────────┐
                     ↓                ↓                ↓
                 ChatLLM          PlanLLM         ToolLLM
                     ↓                ↓                ↓
                 XML解析         日程生成         工具调用
                     ↓                                 ↓
                 回复发送 ←────────────────────────────┘
```

详细架构说明请参考 [架构设计](architecture/overview.md)。

---

## 学习路径

### 新手用户
1. [安装部署](getting-started/installation.md) — 快速安装并运行
2. [配置指南](getting-started/config-guide.md) — 配置 API 密钥和平台适配器
3. [常见问题](getting-started/faq.md) — 解决常见问题

### 开发者
1. [架构总览](architecture/overview.md) — 了解系统整体设计
2. [Pipeline 系统](architecture/pipeline.md) — 理解消息处理流程
3. [插件开发](development/plugin-development.md) — 开发自定义插件
4. [适配器开发](development/adapter-development.md) — 接入新平台

### API 参考
- [Pipeline API](api/pipeline.md) — Pipeline 接口文档
- [Event Bus API](api/event-bus.md) — 事件总线接口
- [Plugin API](api/plugins.md) — 插件系统接口

---

## 开源协议

**[GNU AGPL v3](https://github.com/Qixuan112/Tale-AI/blob/main/LICENSE)** — 自由使用、修改和分发。网络服务提供者必须公开修改后的源代码。

---

## 相关链接

- [GitHub 仓库](https://github.com/Qixuan112/Tale-AI)
- [问题反馈](https://github.com/Qixuan112/Tale-AI/issues)
- [TODO 列表](https://github.com/Qixuan112/Tale-AI/blob/main/TODO.md)
