# 安装部署

## 系统要求

- **Python**: 3.8 或更高版本
- **操作系统**: Windows / Linux / macOS
- **内存**: 建议 2GB 以上
- **网络**: 需要访问 LLM API（如 OpenAI、Claude 等）

## 快速安装

### 1. 克隆仓库

```bash
git clone https://github.com/Qixuan112/Tale-AI.git
cd Tale-AI
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 首次运行

```bash
python main.py
```

首次运行会自动创建配置文件目录 `data/config/`，包含：

- `services.yaml` — LLM API 配置
- `platforms.yaml` — 平台适配器配置
- `character.yaml` — 角色设定
- `behavior.yaml` — 行为配置
- `routing.yaml` — 模型路由配置
- `context.yaml` — 上下文缓存策略（可选）

### 4. 配置 API 密钥

编辑 `data/config/services.yaml`：

```yaml
llm_services:
  chat:
    provider: openai
    api_key: "your-api-key-here"
    model: "gpt-4"
    base_url: "https://api.openai.com/v1"
  
  plan:
    provider: openai
    api_key: "your-api-key-here"
    model: "gpt-3.5-turbo"
  
  tool:
    provider: openai
    api_key: "your-api-key-here"
    model: "gpt-3.5-turbo"
```

详细配置说明请参考 [配置指南](config-guide.md)。

### 5. 访问 WebUI

启动后访问：[http://127.0.0.1:32456](http://127.0.0.1:32456)

首次访问需要输入认证 token（会在启动时打印到控制台）。

## 运行模式

### 完整模式（推荐）

启动 Core + WebUI + 所有已配置的适配器：

```bash
python main.py
```

### 仅 WebUI 模式

适合开发调试，不连接任何平台适配器：

```bash
python webui/app.py
```

### Console 模式

仅启动核心，通过命令行交互（不启动适配器）：

```bash
python main.py
```

然后在控制台直接输入消息测试。

## 配置平台适配器

### QQ（NapCat）

1. 安装并启动 [NapCat](https://github.com/NapNeko/NapCatQQ)
2. 编辑 `data/config/platforms.yaml`：

```yaml
qq:
  enabled: true
  protocol: napcat
  ws_url: "ws://127.0.0.1:3001"
  access_token: "your-token"  # 可选
  bot_qq: "12345678"
```

### WeChat PC（Windows）

仅支持 Windows 系统，需要微信 PC 版。

```yaml
wechat_pc:
  enabled: true
  auto_accept_friend: false
  handle_moments: true  # 是否处理朋友圈
```

### WebSocket 自定义协议

```yaml
websocket:
  enabled: true
  mode: server
  host: "0.0.0.0"
  port: 8765
```

## 验证安装

启动后检查以下内容：

1. **WebUI 可访问** — 打开 http://127.0.0.1:32456
2. **适配器连接成功** — 在 WebUI 的"适配器管理"页面查看状态
3. **聊天测试** — 在 WebUI 的"Chat"页面发送测试消息

## 常见问题

### 依赖安装失败

```bash
# 使用清华镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### WebUI 无法访问

检查端口是否被占用：

```bash
# Windows
netstat -ano | findstr :32456

# Linux/macOS
lsof -i :32456
```

修改端口（编辑 `webui/app.py`）：

```python
WEBUI_PORT = 32456  # 改为其他端口
```

### 适配器连接失败

1. 检查 `platforms.yaml` 配置是否正确
2. 确认平台服务（如 NapCat）已启动
3. 查看 `data/logs/` 目录下的日志文件

更多问题请参考 [常见问题](faq.md)。

## 下一步

- [配置指南](config-guide.md) — 详细配置说明
- [架构概览](../architecture/overview.md) — 了解系统设计
- [插件开发](../development/plugin-development.md) — 开发自定义功能
