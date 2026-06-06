<p align="center">
  <h1>Tale</h1>
  <p><em>AI That Lives a Life of Its Own</em></p>
</p>

---

**Tale** is a multi-agent AI conversation system with autonomous daily planning. The AI character schedules its own day — waking up, working, resting, playing — like a real person. Multi-platform support and a full-featured WebUI dashboard included.

---

## Highlights

- **Multi-Agent Architecture** — ChatLLM (conversation) + PlanLLM (scheduling) + ToolLLM (tool calling)
- **Autonomous Daily Planning** — AI generates 24h schedules simulating real-life routines
- **Tool Calling** — Browser, search, weather, calculator; extensible via plugins
- **WebUI Dashboard** — Real-time chat, config editor, log viewer, adapter management
- **Multi-Platform** — QQ / WeChat PC (incl. Moments) / WebSocket, hot-pluggable adapters
- **Plugin System** — 6 extension points, auto-discovery via manifest.json

> 中文版 README 请见 [docs/README.zh.md](docs/README.zh.md)

---

## Quick Start

```bash
git clone https://github.com/Qixuan112/Tale_ai.git
cd Tale_ai
pip install -r requirements.txt
python main.py              # Start core + WebUI → http://127.0.0.1:32456
```

On first run, config files are auto-created in `data/config/`. Edit `services.yaml` with your API keys and start chatting.
> **Configuration Guide**: See [docs/config-guide.md](docs/config-guide.md) for detailed instructions — YAML vs `.env`, WebUI setup, and common pitfalls.

> **Security**: WebUI binds to localhost by default. Always add authentication behind a reverse proxy before exposing it.

---

## Architecture

```
User Input → ChatLLM (intent) → PlanLLM (plan) / ToolLLM (tools)
                ↕
         EventBus ← Plugin System ← Adapters (QQ/WeChat/WS)
                ↕
           WebUI (Flask) → Dashboard · Chat · Config · Logs
```

---

## Reference

This project's design was partially inspired by [KiraAI](https://github.com/xxynet/KiraAI), a modular AI chatbot framework.

### Third-Party Code

| Component | License | Description |
|-----------|---------|-------------|
| [wxauto](https://github.com/cluic/wxauto) (`core/adapter/src/wechat_pc/wxauto/`) | Apache 2.0 | WeChat PC automation library |
| [UIAutomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) (bundled in wxauto) | Apache 2.0 | Windows UI automation wrapper |

---

## License

**[GNU AGPL v3](LICENSE)** — Free to use, modify, and distribute. Network service providers must disclose modified source code.

---

<p align="center">
  <a href="https://github.com/Qixuan112/Tale_ai">GitHub</a> ·
  <a href="https://github.com/Qixuan112/Tale_ai/issues">Issues</a>
</p>
