# 常见问题

## 安装相关

### Q: pip 安装依赖很慢？

**A**: 使用国内镜像加速：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: 提示 Python 版本过低？

**A**: Tale-AI 需要 Python 3.8+。检查版本：

```bash
python --version
```

如果版本过低，请升级 Python。

### Q: Windows 上提示找不到 Visual C++ 编译器？

**A**: 某些依赖需要编译。安装 [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，或使用预编译的 wheel：

```bash
pip install --only-binary :all: -r requirements.txt
```

## 配置相关

### Q: 如何获取 OpenAI API Key？

**A**: 
1. 访问 [platform.openai.com](https://platform.openai.com/)
2. 注册/登录账号
3. 进入 API Keys 页面生成新密钥
4. 填入 `data/config/services.yaml`

### Q: 支持哪些 LLM 提供商？

**A**: 支持所有兼容 OpenAI API 格式的提供商：
- OpenAI（GPT-3.5/GPT-4）
- Anthropic Claude（通过兼容层）
- Azure OpenAI
- 国内大模型（通义千问、文心一言等，需要兼容 OpenAI 格式）

配置示例：

```yaml
llm_services:
  chat:
    provider: openai
    api_key: "sk-..."
    model: "gpt-4"
    base_url: "https://your-proxy.com/v1"  # 自定义 endpoint
```

### Q: 如何关闭 WebUI 认证？

**A**: 编辑 `webui/app.py`，设置：

```python
WEBUI_AUTH_ENABLED = False
```

**警告**：仅在本地使用时关闭，生产环境务必启用认证。

### Q: 忘记 WebUI Token 怎么办？

**A**: 删除 `data/config/webui_token` 文件，重启程序会重新生成。

## 适配器相关

### Q: QQ 适配器连接失败？

**A**: 检查清单：
1. NapCat 是否已启动？
2. `platforms.yaml` 中的 `ws_url` 是否正确？
3. 如果设置了 `access_token`，确认与 NapCat 配置一致
4. 查看 `data/logs/adapter_qq.log` 了解详细错误

### Q: WeChat PC 适配器在 Windows 11 上不工作？

**A**: 确保：
1. 微信 PC 版已登录
2. 以**管理员权限**运行 Tale-AI
3. 关闭 Windows Defender 的实时保护（可能拦截 UI 自动化）

### Q: 如何禁用某个适配器？

**A**: 编辑 `data/config/platforms.yaml`，设置 `enabled: false`：

```yaml
qq:
  enabled: false  # 禁用 QQ 适配器
```

## 功能相关

### Q: 如何设置唤醒词？

**A**: 编辑 `data/config/behavior.yaml`：

```yaml
wake_words:
  - "@Bot"
  - "Tali"
  - "塔莉"
```

### Q: 如何配置白名单/黑名单？

**A**: 在 `data/config/behavior.yaml` 中：

```yaml
permissions:
  mode: whitelist  # 或 blacklist
  whitelist:
    - "user_id_1"
    - "user_id_2"
  blacklist:
    - "spam_user"
```

### Q: 如何查看日程计划？

**A**: 
1. WebUI → "Plan" 页面
2. 或查看 `data/plans/YYYY-MM-DD.json` 文件

### Q: 工具调用失败？

**A**: 检查：
1. `services.yaml` 中 `tool` LLM 的配置是否正确
2. 工具是否需要额外配置（如搜索需要网络访问）
3. 查看 `data/logs/tool.log` 了解详细错误

## 性能相关

### Q: LLM 响应很慢？

**A**: 
1. 检查网络连接（特别是访问国外 API）
2. 考虑使用更快的模型（如 gpt-3.5-turbo 代替 gpt-4）
3. 启用 Prompt Caching（编辑 `data/config/context.yaml`）

### Q: 内存占用过高？

**A**: 
1. 限制会话历史长度（`data/config/behavior.yaml` 中的 `max_history`）
2. 减少同时运行的适配器数量
3. 定期清理 `data/plans/` 中的旧日程文件

## 调试相关

### Q: 如何查看详细日志？

**A**: 日志位于 `data/logs/` 目录：
- `tale.log` — 主程序日志
- `adapter_*.log` — 各适配器日志
- `webui.log` — WebUI 日志

或在 WebUI 的"日志查看器"页面实时查看。

### Q: 如何开启 Debug 模式？

**A**: 运行时设置环境变量：

```bash
# Windows
set TALE_DEBUG=1
python main.py

# Linux/macOS
TALE_DEBUG=1 python main.py
```

### Q: 遇到 Bug 如何反馈？

**A**: 
1. 收集日志文件（`data/logs/`）
2. 记录复现步骤
3. 在 [GitHub Issues](https://github.com/Qixuan112/Tale-AI/issues) 提交 Bug 报告

## 插件相关

### Q: 如何安装插件？

**A**: 
1. 将插件目录放到 `plugins/` 下
2. 确保包含 `manifest.json` 和 `plugin.py`
3. 重启 Tale-AI

插件结构示例：

```
plugins/
└── my_plugin/
    ├── manifest.json
    └── plugin.py
```

### Q: 插件加载失败？

**A**: 检查：
1. `manifest.json` 格式是否正确
2. `plugin.py` 中是否实现了 `load(manager)` 函数
3. 查看 `data/logs/tale.log` 中的插件加载日志

## 其他问题

### Q: 支持多账号吗？

**A**: 支持。每个平台适配器可以连接一个账号，多个适配器可以同时运行。

### Q: 可以部署在服务器上吗？

**A**: 可以。建议：
1. 使用 `screen` 或 `tmux` 后台运行
2. WebUI 通过 Nginx 反向代理，启用 HTTPS
3. 配置防火墙规则

### Q: 数据存储在哪里？

**A**: 
- 配置文件：`data/config/`
- 日程计划：`data/plans/`
- 会话历史：`data/sessions/`
- 日志文件：`data/logs/`

## 仍有问题？

- 查看 [GitHub Issues](https://github.com/Qixuan112/Tale-AI/issues)
- 提交新的 Issue 描述你的问题
- 加入社区讨论（如果有的话）
