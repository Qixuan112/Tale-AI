# 配置填写指南

## 两种配置方式

Tale-AI 支持 YAML 文件和 `.env` 环境变量两种配置方式，两者可以叠加使用。

| 方式 | 优先级 | 适用场景 |
|------|--------|----------|
| **环境变量** (`.env`) | 高 | Docker 部署、不想在文件里写 API Key |
| **YAML** (`data/config/`) | 低 | 日常使用、WebUI 面板配置 |

环境变量会覆盖 YAML 中的同名字段。

---

## 方式一：环境变量（推荐快速上手）

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
TALE_CHAT_API_KEY=sk-your-key-here
TALE_CHAT_MODEL=deepseek-chat
TALE_CHAT_URL=https://api.deepseek.com/v1

TALE_PLAN_API_KEY=sk-your-key-here
TALE_PLAN_MODEL=deepseek-chat
TALE_PLAN_URL=https://api.deepseek.com/v1

TALE_TOOL_API_KEY=sk-your-key-here
TALE_TOOL_MODEL=deepseek-chat
TALE_TOOL_URL=https://api.deepseek.com/v1
```

三个 LLM 可以用同一家服务商的同一把 Key，也可以用不同的。

---

## 方式二：WebUI 面板配置

启动后打开 `http://127.0.0.1:32456`，进入 **配置** 页面：

1. **服务提供商** — 填写 API Key、模型名、Base URL
2. **模型路由** — 指定 Chat/Plan/Tool 各用哪个提供商
3. **角色人设** — 编辑 AI 角色的名字、性格、对话风格
4. **行为设置** — 调整唤醒词、上下文长度、打字速度等

保存后自动热重载，无需重启。

> 如果路由未配置但有可用提供商，系统会自动回退到第一个。

---

## YAML 文件一览

首次启动后自动创建在 `data/config/`：

| 文件 | 内容 |
|------|------|
| `services.yaml` | API Key、模型名、Base URL、超时时间 |
| `routing.yaml` | Chat/Plan/Tool 各用哪个提供商 |
| `character.yaml` | 角色名、性别、年龄、性格、对话示例 |
| `behavior.yaml` | 唤醒词、上下文长度、延迟、打字速度 |
| `platforms.yaml` | QQ/微信/WebSocket 连接配置 |
| `plugins.yaml` | 插件启用开关 |

### services.yaml 示例

```yaml
deepseek:
  type: chat
  format: openai
  api_key: "sk-your-key"
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-chat"
```

### routing.yaml 示例

```yaml
main_llm:
  provider: deepseek
plan_llm:
  provider: deepseek
tool_llm:
  provider: deepseek
```

---

## 常见问题

### 启动后提示 "Missing credentials"？

API Key 未配置。确认 `services.yaml` 或 `.env` 中已填写 Key，然后重启或通过 WebUI 保存配置。

### 配置完还是读不到？

检查优先级：环境变量会**覆盖** YAML。如果你同时设置了 `.env` 和 `services.yaml`，以 `.env` 为准。

### 没有 WebUI 怎么配置？

直接编辑 `data/config/services.yaml`，然后重启。或者用 `.env` 方式。
