"""
Tale WebUI - Flask 管理面板
============================
技术栈: Flask + Jinja2 + 原生 JS
"""

import os
import sys
import secrets
import string
import shutil
import tempfile

from core.utils import get_logger
logger = get_logger(__name__)

# Windows 控制台 UTF-8 编码修复
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
import uuid
import yaml
import asyncio
import logging
import logging.handlers
import queue
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from core.utils import get_logger
logger = get_logger(__name__)

from flask import Flask, render_template, jsonify, request, Response, session, redirect

# 把项目根目录加入路径，确保能导入 core
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.llm.chatllm import ChatLLM
from core.llm.planllm import PlanLLM, get_planllm
from core.config.provide import config_loader, get_character_prompt
from core.function_caller import AVAILABLE_TOOLS, execute_function
from core.adapter.manager import AdapterManager
from core.main import get_core, get_main_event_loop
from core.tools.registry import get_registry

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['JSON_AS_ASCII'] = False
app.add_template_global(lambda x: x, '_')
def _load_secret_key() -> str:
    """Load persistent secret key from file, generating if needed."""
    key_path = PROJECT_ROOT / "data" / "config" / "secret_key"
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(32)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key, encoding="utf-8")
    return key


app.secret_key = _load_secret_key()


def _generate_csrf_token() -> str:
    """Get or create CSRF token for the current session."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']

# ============ WebUI 认证 ============

WEBUI_AUTH_ENABLED = True  # 设为 False 可跳过认证（桌面端嵌入时不需要）

_TOKEN_CHARS = string.ascii_letters + string.digits


def _generate_token() -> str:
    return ''.join(secrets.choice(_TOKEN_CHARS) for _ in range(16))


def _load_webui_token() -> str:
    token_path = PROJECT_ROOT / "data" / "config" / "webui_token"
    if token_path.exists():
        print(f"\n  WebUI 认证令牌文件：{token_path}")
        return token_path.read_text(encoding="utf-8").strip()
    # 首次启动自动生成
    token = _generate_token()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")
    print(f"\n  WebUI 认证令牌（首次启动）: {token}")
    return token


WEBUI_TOKEN = _load_webui_token()

# 登录限速：ip -> {"count": int, "window_start": float, "blocked_until": float}
_login_attempts: dict = {}
_login_attempts_lock = threading.Lock()


def _check_login_rate_limit() -> Optional[str]:
    """检查登录频率限制，返回错误信息或 None"""
    import time
    client_ip = request.remote_addr or "unknown"
    now = time.time()
    with _login_attempts_lock:
        record = _login_attempts.get(client_ip)
        if record:
            if record.get("blocked_until", 0) > now:
                remaining = int(record["blocked_until"] - now)
                return f"登录尝试过于频繁，请 {remaining} 秒后再试"
            if now - record["window_start"] > 60:
                record["count"] = 0
                record["window_start"] = now
        else:
            _login_attempts[client_ip] = {"count": 0, "window_start": now, "blocked_until": 0}
    return None


def _record_login_attempt(success: bool) -> None:
    import time
    client_ip = request.remote_addr or "unknown"
    now = time.time()
    with _login_attempts_lock:
        record = _login_attempts.get(client_ip)
        if not record:
            return
        if success:
            _login_attempts.pop(client_ip, None)
            return
        record["count"] += 1
        if record["count"] >= 3:
            block_time = min(30 * (2 ** (record["count"] - 3)), 3600)
            record["blocked_until"] = now + block_time


@app.before_request
def _require_auth():
    if not WEBUI_AUTH_ENABLED:
        return
    if request.path in ("/login", "/api/login"):
        return
    if request.path.startswith("/static/"):
        return
    if "webui_authed" not in session:
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return redirect("/login")


@app.context_processor
def inject_plugin_nav():
    """注入插件侧边栏导航项到所有模板"""
    try:
        from core.plugin import PluginManager
        items = PluginManager._nav_items
    except Exception:
        items = []
    return {"plugin_nav_items": items}


@app.before_request
def _check_csrf():
    """CSRF protection for state-changing API routes."""
    if request.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
        return
    if request.path.startswith('/static/'):
        return
    if request.path == '/api/login':
        return
    token = request.headers.get('X-CSRF-Token')
    if not token or token != session.get('csrf_token'):
        return jsonify({"ok": False, "error": "CSRF token mismatch"}), 403


@app.after_request
def _set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.context_processor
def inject_csrf_token():
    return {'csrf_token': _generate_csrf_token()}


# 线程池，用于执行同步的 LLM 调用
_executor = ThreadPoolExecutor(max_workers=4)

# ============ 全局组件初始化 ============

def _init_chatllm():
    """初始化 ChatLLM（独立实例，与核心进程不冲突）"""
    cfg = config_loader.chat_api
    if not cfg.get("api_key"):
        return None
    return ChatLLM(
        api_key=cfg["api_key"],
        model=cfg["model"],
        url=cfg["url"],
        max_context=config_loader.max_context
    )


CONVERSATIONS_DIR = Path(PROJECT_ROOT) / "data" / "conversations"
CONVERSATIONS_INDEX = CONVERSATIONS_DIR / "index.json"


class ConversationStore:
    """会话管理器：持久化到磁盘，WebUI 重启后对话记录不丢失"""

    def __init__(self, chatllm: ChatLLM):
        self.chatllm = chatllm
        self.conversations = []  # 元数据列表
        self.current_id = None
        self._messages = {}  # conv_id -> messages list

        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

        # 如果没有任何会话，创建默认会话
        if not self.conversations:
            self.create("默认会话")

    # ===== 持久化：保存 / 加载 =====

    def _save_index(self):
        """将会话元数据列表写入 index.json"""
        data = {
            "current_id": self.current_id,
            "conversations": self.conversations
        }
        with open(CONVERSATIONS_INDEX, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _message_file(self, conv_id: int) -> Path:
        return CONVERSATIONS_DIR / f"conv_{conv_id}.json"

    def _save_messages(self, conv_id: int):
        """将指定会话的消息写入独立文件"""
        msgs = self._messages.get(conv_id, [])
        with open(self._message_file(conv_id), "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)

    def _load_from_disk(self):
        """从磁盘恢复所有会话数据"""
        # 1. 加载索引
        if CONVERSATIONS_INDEX.exists():
            try:
                with open(CONVERSATIONS_INDEX, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.conversations = data.get("conversations", [])
                self.current_id = data.get("current_id")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[ConversationStore] 索引文件损坏，将重建: {e}")
                self.conversations = []
                self.current_id = None

        # 2. 加载每个会话的消息
        for conv in self.conversations:
            cid = conv["id"]
            msg_file = self._message_file(cid)
            if msg_file.exists():
                try:
                    with open(msg_file, "r", encoding="utf-8") as f:
                        self._messages[cid] = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"[ConversationStore] 会话 {cid} 消息文件损坏: {e}")
                    self._messages[cid] = []

        # 3. 如果存在 current_id，将对应消息恢复到 ChatLLM
        if self.chatllm and self.current_id is not None:
            if self.current_id in self._messages:
                self.chatllm.set_history(list(self._messages[self.current_id]))
            else:
                self.chatllm.clear_history()

    # ===== 会话管理 =====

    def create(self, title="新对话"):
        if self.current_id is not None and self.chatllm:
            self._messages[self.current_id] = self.chatllm.get_history()
            self._save_messages(self.current_id)

        # 生成不重复的 id（用当前最大 id +1，兼容已删除的间隙）
        existing_ids = {c["id"] for c in self.conversations}
        conv_id = 1
        while conv_id in existing_ids:
            conv_id += 1

        now = datetime.now()
        conv = {
            "id": conv_id,
            "title": title,
            "last_message": "",
            "time": now.strftime("%H:%M"),
            "count": 0,
            "created_at": now.isoformat()
        }
        self.conversations.append(conv)
        self.current_id = conv_id

        # 重置 ChatLLM，保留 system 消息
        if self.chatllm:
            self.chatllm.clear_history()
            self._messages[conv_id] = self.chatllm.get_history()
            self._save_messages(conv_id)

        self._save_index()
        return conv

    def switch(self, conv_id: int):
        if conv_id == self.current_id:
            return
        if self.chatllm is None:
            return
        # 保存当前会话消息
        if self.current_id is not None:
            self._messages[self.current_id] = self.chatllm.get_history()
            self._save_messages(self.current_id)
        # 恢复目标会话消息
        if conv_id in self._messages:
            self.chatllm.set_history(list(self._messages[conv_id]))
        else:
            self.chatllm.clear_history()
        self.current_id = conv_id
        self._save_index()

    def _get_conv(self, conv_id: int):
        """通过 id 查找会话元数据"""
        for c in self.conversations:
            if c["id"] == conv_id:
                return c
        return None

    def send(self, text: str, images: list = None) -> str:
        if self.chatllm is None:
            return "[错误] ChatLLM 未初始化，请检查 services.yaml 配置"
        if self.current_id is None:
            self.create()

        conv = self._get_conv(self.current_id)
        if conv:
            conv["last_message"] = text[:60] if text else "[图片]"
            conv["time"] = datetime.now().strftime("%H:%M")

        # 持久化用户消息
        self._messages[self.current_id] = self.chatllm.get_history()
        self._save_messages(self.current_id)
        self._save_index()

        # 图片识别—有图时用 VLM 识别后注入
        full_text = text or ""
        if images:
            try:
                from core.llm.vlm import get_vlm_llm
                vlm = get_vlm_llm()
                vlm_result = vlm.chat_with_image(full_text, images)
                if vlm_result:
                    full_text = f"{full_text}\n\n[图片识别结果]\n{vlm_result}"
            except Exception as e:
                logger.warning("VLM 图片识别失败: %s", e)

        # 在线程池中执行阻塞的 LLM 调用
        future = _executor.submit(self.chatllm.chat, full_text)
        try:
            reply = future.result()
        except Exception as e:
            self._messages[self.current_id] = self.chatllm.get_history()
            self._save_messages(self.current_id)
            raise e

        if conv:
            conv["count"] = len(self.chatllm.get_history()) - 1  # 不含 system

        # 持久化：保存元数据和含回复的完整消息
        self._messages[self.current_id] = self.chatllm.get_history()
        self._save_messages(self.current_id)
        self._save_index()

        return reply

    def history(self, conv_id=None):
        cid = conv_id or self.current_id
        if cid == self.current_id and self.chatllm:
            return self.chatllm.get_history()
        return list(self._messages.get(cid, []))

    def clear(self, conv_id=None):
        cid = conv_id or self.current_id
        if self.chatllm and cid == self.current_id:
            # clear_history() 内部持锁，重置到仅剩 system 消息
            self.chatllm.clear_history()
            msgs = self.chatllm.get_history()
            self._messages[cid] = msgs
            conv = self._get_conv(cid)
            if conv:
                conv["count"] = 0
                conv["last_message"] = ""
            # 持久化
            self._save_messages(cid)
            self._save_index()

    def delete(self, conv_id: int):
        """删除指定会话及其消息文件"""
        if conv_id not in {c["id"] for c in self.conversations}:
            return False

        # 从消息缓存和磁盘移除
        if conv_id in self._messages:
            del self._messages[conv_id]
        msg_file = self._message_file(conv_id)
        if msg_file.exists():
            msg_file.unlink()

        # 从元数据列表移除
        self.conversations = [c for c in self.conversations if c["id"] != conv_id]

        # 如果删除的是当前会话，先更新 current_id 再切换，避免 switch 重新保存已删会话
        if conv_id == self.current_id:
            self.current_id = None  # 防止 switch 中 _save_messages 误保存
            if self.conversations:
                self.switch(self.conversations[0]["id"])
            else:
                if self.chatllm:
                    self.chatllm.clear_history()

        self._save_index()
        return True

    def to_list(self):
        return self.conversations


# 初始化
_chatllm = _init_chatllm()
conv_store = ConversationStore(_chatllm)
_planllm = get_planllm()

# 适配器管理器（通过核心共享实例，WebUI 控制启停）
def _get_adapter_manager():
    """获取核心的适配器管理器"""
    try:
        core = get_core()
        if core and core.adapter_bridge:
            return core.adapter_bridge.get_manager()
    except Exception:
        pass
    return None

# 日志：内存队列（用于 SSE）+ 文件持久化
MAX_LOGS = 500
LOG_QUEUE = queue.Queue(maxsize=MAX_LOGS)
LOG_FILE = Path(PROJECT_ROOT) / "data" / "logs" / "webui.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
_log_lock = threading.Lock()

# RotatingFileHandler 用于自动轮转（但实际写入走 emit）
_log_rotator = logging.handlers.RotatingFileHandler(
    filename=str(LOG_FILE),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
# 关闭 RotatingFileHandler 自带的日志流（我们手动管理写入）
_log_rotator.close()


def _put_log(record_dict):
    """写入日志：文件持久化（自动轮转）+ 内存队列"""
    # 文件持久化（手动轮转检查 + 写入）
    try:
        ts = record_dict.get("time", "")
        lvl = record_dict.get("level", "INFO")
        mod = record_dict.get("module", "")
        msg = record_dict.get("message", "")
        line = f"[{ts}] [{lvl}] [{mod}] {msg}\n"
        with _log_lock:
            # 检查是否需要轮转
            try:
                if LOG_FILE.stat().st_size > _log_rotator.maxBytes:
                    _log_rotator.doRollover()
            except OSError:
                pass
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
    # 内存队列（用于 SSE 实时推送）
    try:
        LOG_QUEUE.put_nowait(record_dict)
    except queue.Full:
        try:
            LOG_QUEUE.get_nowait()
            LOG_QUEUE.put_nowait(record_dict)
        except queue.Empty:
            pass

# 内存级指标缓存（Dashboard 实时数据）
_metrics_cache = {
    "messages_last_hour": 0,
    "llm_calls_last_hour": 0,
    "errors_last_hour": 0,
}


# ============ 页面路由 ============

@app.route("/login")
def page_login():
    if "webui_authed" in session:
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/")
def index():
    if WEBUI_AUTH_ENABLED and "webui_authed" not in session:
        return redirect("/login")
    return render_template("chat.html")


@app.route("/dashboard")
def page_dashboard():
    return render_template("dashboard.html")


@app.route("/chat")
def page_chat():
    return render_template("chat.html")


@app.route("/plan")
def page_plan():
    return render_template("plan.html")


@app.route("/config")
def page_config():
    return render_template("config.html")


@app.route("/adapter")
def page_adapter():
    return render_template("adapter.html")


@app.route("/tools")
def page_tools():
    return render_template("tools.html")


@app.route("/plugins")
def page_plugins():
    return render_template("plugins.html")


@app.route("/knowledge")
def page_knowledge():
    return render_template("knowledge.html")


@app.route("/logs")
def page_logs():
    return render_template("logs.html")


@app.route("/sessions")
def page_sessions():
    return render_template("sessions.html")


# ============ API：系统状态 ============

def _detect_offline_reason() -> str:
    """检测 ChatLLM 离线的原因"""
    cfg = config_loader.chat_api
    if not cfg.get("api_key"):
        return "missing_api_key"
    return "unknown"

@app.route("/api/status")
def api_status():
    running = _chatllm is not None
    offline_reason = None if running else _detect_offline_reason()
    mem = None
    try:
        import psutil
        mem = psutil.virtual_memory().percent
    except Exception:
        pass

    # 构建告警列表
    alerts = []
    manager = _get_adapter_manager()
    adapters = manager.list_running_adapters() if manager else []
    all_adapters = AdapterManager.list_adapters() if manager else []
    # 简单告警：内存过高
    if mem is not None and mem > 85:
        alerts.append({"level": "danger", "key": "high_memory", "message": f"内存占用过高: {mem:.1f}%"})

    # routing 未配置但 services 已配置时提醒
    providers = config_loader.providers
    has_services = any(
        p.api_key for p in providers.values()
    )
    routing_provider = config_loader.models.main_llm.provider
    if has_services and not routing_provider:
        alerts.append({
            "level": "warning",
            "key": "routing_not_configured",
            "message": "模型路由未配置，已自动使用第一个可用服务商，建议前往路由设置明确指定"
        })

    return jsonify({
        "running": running,
        "offline_reason": offline_reason,
        "time": datetime.now().isoformat(),
        "conversations": len(conv_store.conversations),
        "adapters": adapters,
        "memory": mem,
        "metrics": {
            "messages_last_hour": _metrics_cache["messages_last_hour"],
            "llm_calls_last_hour": _metrics_cache["llm_calls_last_hour"],
            "errors_last_hour": _metrics_cache["errors_last_hour"]
        },
        "alerts": alerts
    })


# ============ API：对话管理 ============

@app.route("/api/chat/conversations")
def api_chat_conversations():
    return jsonify(conv_store.to_list())


@app.route("/api/chat/history/<int:conv_id>")
def api_chat_history(conv_id):
    return jsonify(conv_store.history(conv_id))


@app.route("/api/chat/history", methods=["DELETE"])
def api_chat_clear():
    conv_store.clear()
    return jsonify({"ok": True})


@app.route("/api/chat/send", methods=["POST"])
def api_chat_send():
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    conv_id = data.get("conv_id")
    images = data.get("images", [])

    if not message and not images:
        return jsonify({"error": "Message cannot be empty"}), 400

    if conv_id is not None and conv_id != conv_store.current_id:
        conv_store.switch(conv_id)

    try:
        reply = conv_store.send(message, images=images)
        return jsonify({"reply": reply, "conv_id": conv_store.current_id})
    except Exception as e:
        logger.error("发送消息失败: %s", e, exc_info=True)
        return jsonify({"error": f"发送消息失败: {e}"}), 500


@app.route("/api/chat/new", methods=["POST"])
def api_chat_new():
    data = request.get_json() or {}
    title = data.get("title", "新对话")
    conv = conv_store.create(title)
    return jsonify(conv)


@app.route("/api/chat/<int:conv_id>", methods=["DELETE"])
def api_chat_delete(conv_id):
    ok = conv_store.delete(conv_id)
    if not ok:
        return jsonify({"ok": False, "error": "会话不存在"}), 404
    return jsonify({"ok": True})


# ============ API：日程规划 ============

@app.route("/api/plan/today")
def api_plan_today():
    _planllm.ensure_today_plan()
    plan = _planllm.get_today_plan()
    if plan:
        return jsonify(plan.to_dict())
    return jsonify({"date": datetime.now().date().isoformat(), "entries": [], "summary": ""})


@app.route("/api/plan/<date_str>")
def api_plan_date(date_str):
    """date_str: YYYY-MM-DD"""
    today_str = datetime.now().date().isoformat()
    # 如果请求的是今天的日期且无计划，自动生成
    if date_str == today_str:
        _planllm.ensure_today_plan()
        plan = _planllm.get_today_plan()
        if plan:
            return jsonify(plan.to_dict())
    file_path = Path("data/diary") / f"plan_{date_str}.json"
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"date": date_str, "entries": [], "summary": ""})


@app.route("/api/plan/generate", methods=["POST"])
def api_plan_generate():
    data = request.get_json() or {}
    prompt = data.get("prompt", "制定今天的计划")
    result = _planllm.generate_daily_plan(prompt)
    plan = _planllm.get_today_plan()
    return jsonify({"result": result, "plan": plan.to_dict() if plan else None})


@app.route("/api/plan/event", methods=["POST"])
def api_plan_add_event():
    data = request.get_json() or {}
    req_text = data.get("request", "")
    if not req_text:
        return jsonify({"error": "Missing request content"}), 400
    result = _planllm.add_event_from_request(req_text)
    return jsonify({"result": result})


@app.route("/api/plan/event/<entry_id>", methods=["DELETE"])
def api_plan_delete_event(entry_id):
    ok = _planllm.remove_event(entry_id)
    return jsonify({"ok": ok})


# ============ API：配置中心 ============

# 使用 ConfigLoader 的绝对路径避免 CWD 依赖
from core.config.loader import config_loader as _cl
CONFIG_DIR = Path(_cl._data_dir) / "config"
CONFIG_FILES = {
    "character": "character.yaml",
    "behavior": "behavior.yaml",
    "platforms": "platforms.yaml",
    "services": "services.yaml",
    "routing": "routing.yaml",
    "plugins": "plugins.yaml",
}


@app.route("/api/config")
def api_config_list():
    configs = []
    for key, filename in CONFIG_FILES.items():
        configs.append({"name": key, "label": filename.replace('.yaml', '')})
    return jsonify(configs)


@app.route("/api/config/<name>")
def api_config_get(name):
    if name not in CONFIG_FILES:
        return jsonify({"error": "Unknown config"}), 404
    path = CONFIG_DIR / CONFIG_FILES[name]
    if not path.exists():
        return jsonify({})
    with open(path, "r", encoding="utf-8") as f:
        return jsonify(yaml.safe_load(f) or {})


@app.route("/api/config/<name>", methods=["POST"])
def api_config_save(name):
    if name not in CONFIG_FILES:
        return jsonify({"error": "Unknown config"}), 404
    data = request.get_json()
    if data is None:
        return jsonify({"error": "Invalid data"}), 400
    path = CONFIG_DIR / CONFIG_FILES[name]
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix=".tmp_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    config_loader.reload()
    return jsonify({"ok": True})


# ============ API：人设预设 + 导入导出 + 源码模式 ============

PRESETS_DIR = CONFIG_DIR / "presets"


@app.route("/api/config/presets")
def api_config_presets_list():
    """列出所有预设"""
    PRESETS_DIR.mkdir(exist_ok=True)
    presets = []
    for f in sorted(PRESETS_DIR.glob("*.yaml")):
        presets.append({
            "name": f.stem,
            "file": f.name,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        })
    return jsonify(presets)


@app.route("/api/config/presets", methods=["POST"])
def api_config_presets_save():
    """保存当前人设为预设"""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "预设名称不能为空"}), 400
    PRESETS_DIR.mkdir(exist_ok=True)
    char_path = CONFIG_DIR / "character.yaml"
    if not char_path.exists():
        return jsonify({"ok": False, "error": "character.yaml 不存在"}), 404
    content = char_path.read_text(encoding="utf-8")
    preset_path = PRESETS_DIR / f"{name}.yaml"
    preset_path.write_text(content, encoding="utf-8")
    return jsonify({"ok": True, "name": name})


@app.route("/api/config/presets/<name>/apply", methods=["POST"])
def api_config_presets_apply(name):
    """应用预设（复制到 character.yaml）"""
    PRESETS_DIR.mkdir(exist_ok=True)
    preset_path = PRESETS_DIR / f"{name}.yaml"
    if not preset_path.exists():
        return jsonify({"ok": False, "error": "预设不存在"}), 404
    content = preset_path.read_text(encoding="utf-8")
    char_path = CONFIG_DIR / "character.yaml"
    char_path.write_text(content, encoding="utf-8")
    config_loader.reload()
    return jsonify({"ok": True})


@app.route("/api/config/presets/<name>", methods=["DELETE"])
def api_config_presets_delete(name):
    """删除预设"""
    PRESETS_DIR.mkdir(exist_ok=True)
    preset_path = PRESETS_DIR / f"{name}.yaml"
    if preset_path.exists():
        preset_path.unlink()
    return jsonify({"ok": True})


@app.route("/api/config/<name>/raw")
def api_config_get_raw(name):
    """获取配置文件的原始 YAML 文本（源码模式用）"""
    if name not in CONFIG_FILES:
        return jsonify({"error": "Unknown config"}), 404
    path = CONFIG_DIR / CONFIG_FILES[name]
    if not path.exists():
        return "", 200, {"Content-Type": "text/plain; charset=utf-8"}
    content = path.read_text(encoding="utf-8")
    return content, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/api/config/<name>/raw", methods=["POST"])
def api_config_save_raw(name):
    """保存原始 YAML 文本到配置文件（源码模式用）"""
    if name not in CONFIG_FILES:
        return jsonify({"error": "Unknown config"}), 404
    content = request.get_data(as_text=True)
    if content is None:
        return jsonify({"error": "Invalid data"}), 400
    path = CONFIG_DIR / CONFIG_FILES[name]
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix=".tmp_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    config_loader.reload()
    return jsonify({"ok": True})


@app.route("/api/config/export")
def api_config_export():
    """导出 character.yaml"""
    path = CONFIG_DIR / "character.yaml"
    if not path.exists():
        return jsonify({"error": "character.yaml 不存在"}), 404
    content = path.read_text(encoding="utf-8")
    date_str = datetime.now().strftime("%Y-%m-%d")
    return Response(
        content,
        mimetype="text/yaml",
        headers={
            "Content-Disposition": f'attachment; filename="character_{date_str}.yaml"'
        }
    )


@app.route("/api/config/import", methods=["POST"])
def api_config_import():
    """导入角色配置文件（替换 character.yaml）"""
    file = request.files.get("file")
    if not file:
        return jsonify({"ok": False, "error": "没有上传文件"}), 400
    content = file.read().decode("utf-8")
    # 验证 YAML 格式
    try:
        yaml.safe_load(content)
    except Exception as e:
        return jsonify({"ok": False, "error": f"YAML 格式错误: {e}"}), 400
    path = CONFIG_DIR / "character.yaml"
    path.write_text(content, encoding="utf-8")
    config_loader.reload()
    return jsonify({"ok": True})


def _load_platforms_data():
    """加载 platforms.yaml"""
    platforms_path = CONFIG_DIR / "platforms.yaml"
    if platforms_path.exists():
        with open(platforms_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# ============ API：适配器管理 ============

@app.route("/api/adapters")
def api_adapters():
    """返回已添加的适配器实例列表（从 platforms.yaml 读取）"""
    platforms_data = _load_platforms_data()
    manager = _get_adapter_manager()
    running = manager.list_running_adapters() if manager else []
    result = []
    for instance_name, config in platforms_data.items():
        adapter_type = config.get("adapter_type", instance_name)
        info = AdapterManager.get_adapter_info(adapter_type) or {}
        result.append({
            "instance_name": instance_name,
            "adapter_type": adapter_type,
            "name": info.get("name", adapter_type),
            "version": info.get("version", "unknown"),
            "author": info.get("author", "unknown"),
            "description": info.get("description", ""),
            "running": instance_name in running
        })
    return jsonify(result)


@app.route("/api/adapters/available")
def api_adapters_available():
    """获取所有可用适配器类型（含配置schema）"""
    manager = _get_adapter_manager()
    all_ids = AdapterManager.list_adapters() if manager else []
    result = []
    for aid in all_ids:
        info = AdapterManager.get_adapter_info(aid)
        schema = AdapterManager.get_schema(aid) if manager else []
        result.append({
            "id": aid,
            **info,
            "schema": schema
        })
    return jsonify(result)


@app.route("/api/adapters/<aid>/add", methods=["POST"])
def api_adapter_add(aid):
    """添加并启动适配器：保存配置到 platforms.yaml 后启动"""
    data = request.get_json() or {}
    config_dict = data.get("config", {})
    instance_name = data.get("instance_name", "").strip()
    if not instance_name:
        instance_name = aid

    # 1. 保存到 platforms.yaml
    platforms_data = _load_platforms_data()

    # 确保实例名唯一
    base_name = instance_name
    counter = 1
    while instance_name in platforms_data:
        instance_name = f"{base_name}_{counter}"
        counter += 1

    # 构建适配器配置块
    adapter_entry = {"enabled": True, "adapter_type": aid, **config_dict}
    platforms_data[instance_name] = adapter_entry

    with open(CONFIG_DIR / "platforms.yaml", "w", encoding="utf-8") as f:
        yaml.dump(platforms_data, f, allow_unicode=True, sort_keys=False)

    # 2. 重新加载配置
    try:
        config_loader.reload()
    except Exception as e:
        return jsonify({"ok": False, "error": f"配置重载失败: {e}"}), 500

    # 3. 启动适配器
    try:
        manager = _get_adapter_manager()
        if manager:
            main_loop = get_main_event_loop()
            if main_loop and main_loop.is_running():
                # 使用主事件循环提交异步任务
                future = asyncio.run_coroutine_threadsafe(
                    manager.start_adapter(instance_name, config_dict, adapter_type=aid),
                    main_loop
                )
                ok = future.result(timeout=30)
            else:
                # 兜底：创建临时事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                ok = loop.run_until_complete(
                    manager.start_adapter(instance_name, config_dict, adapter_type=aid)
                )
                loop.close()
            return jsonify({"ok": ok, "instance_name": instance_name})
        return jsonify({"ok": False, "error": "核心适配器管理器未就绪"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/adapters/<instance_name>/start", methods=["POST"])
def api_adapter_start(instance_name):
    """启动指定实例（从 platforms.yaml 读取配置）"""
    platforms_data = _load_platforms_data()
    config = platforms_data.get(instance_name, {})
    if not config:
        return jsonify({"ok": False, "error": "实例不存在"})

    adapter_type = config.get("adapter_type", instance_name)
    config_dict = {k: v for k, v in config.items() if k not in ("enabled", "adapter_type")}

    # 兼容旧配置：若实例名就是适配器类型且无 adapter_type，尝试从 provide 读取
    if not config_dict and adapter_type == instance_name:
        adapters_cfg = config_loader.adapters
        if instance_name == "qq" and adapters_cfg.qq.enabled:
            q = adapters_cfg.qq
            config_dict = {
                "ws_url": q.ws_uri or "ws://localhost:3001",
                "http_url": q.ws_uri.replace("ws://", "http://").replace("wss://", "https://") if q.ws_uri else "http://localhost:3000",
                "access_token": q.ws_token or "",
                "permission_mode": q.permission_mode,
                "group_allow_list": q.group_allow_list,
                "user_allow_list": q.user_allow_list,
                "bot_pid": q.bot_pid,
                "owner_pid": q.owner_pid,
            }

    try:
        manager = _get_adapter_manager()
        if manager:
            main_loop = get_main_event_loop()
            if main_loop and main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    manager.start_adapter(instance_name, config_dict, adapter_type=adapter_type),
                    main_loop
                )
                ok = future.result(timeout=30)
            else:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                ok = loop.run_until_complete(
                    manager.start_adapter(instance_name, config_dict, adapter_type=adapter_type)
                )
                loop.close()
            return jsonify({"ok": ok})
        return jsonify({"ok": False, "error": "核心适配器管理器未就绪"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/adapters/<instance_name>/stop", methods=["POST"])
def api_adapter_stop(instance_name):
    try:
        manager = _get_adapter_manager()
        if manager:
            main_loop = get_main_event_loop()
            if main_loop and main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    manager.stop_adapter(instance_name),
                    main_loop
                )
                ok = future.result(timeout=30)
            else:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                ok = loop.run_until_complete(manager.stop_adapter(instance_name))
                loop.close()
            return jsonify({"ok": ok})
        return jsonify({"ok": False, "error": "核心适配器管理器未就绪"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/adapters/<instance_name>/config")
def api_adapter_get_config(instance_name):
    """获取适配器实例的当前配置"""
    platforms_data = _load_platforms_data()
    config = platforms_data.get(instance_name, {})
    if not config:
        return jsonify({"error": "实例不存在"}), 404
    adapter_type = config.get("adapter_type", instance_name)
    manager = _get_adapter_manager()
    schema = AdapterManager.get_schema(adapter_type) if manager else []
    config_dict = {k: v for k, v in config.items() if k not in ("enabled", "adapter_type")}
    return jsonify({
        "instance_name": instance_name,
        "adapter_type": adapter_type,
        "config": config_dict,
        "schema": schema
    })


@app.route("/api/adapters/<instance_name>/config", methods=["POST"])
def api_adapter_save_config(instance_name):
    """保存适配器实例配置到 platforms.yaml"""
    data = request.get_json() or {}
    config_dict = data.get("config", {})

    platforms_data = _load_platforms_data()
    if instance_name not in platforms_data:
        return jsonify({"ok": False, "error": "实例不存在"}), 404

    old_config = platforms_data[instance_name]
    adapter_type = old_config.get("adapter_type", instance_name)

    # 保留 enabled 和 adapter_type，更新其余配置
    new_config = {"enabled": old_config.get("enabled", True), "adapter_type": adapter_type, **config_dict}
    platforms_data[instance_name] = new_config

    with open(CONFIG_DIR / "platforms.yaml", "w", encoding="utf-8") as f:
        yaml.dump(platforms_data, f, allow_unicode=True, sort_keys=False)

    try:
        config_loader.reload()
    except Exception as e:
        return jsonify({"ok": False, "error": f"配置重载失败: {e}"}), 500

    return jsonify({"ok": True})


@app.route("/api/adapters/<instance_name>/delete", methods=["POST"])
def api_adapter_delete(instance_name):
    """删除适配器实例（从 platforms.yaml 移除，如运行中先停止）"""
    platforms_data = _load_platforms_data()
    if instance_name not in platforms_data:
        return jsonify({"ok": False, "error": "实例不存在"}), 404

    # 如运行中先停止
    manager = _get_adapter_manager()
    if manager:
        running = manager.list_running_adapters()
        if instance_name in running:
            try:
                main_loop = get_main_event_loop()
                if main_loop and main_loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        manager.stop_adapter(instance_name),
                        main_loop
                    )
                    future.result(timeout=30)
                else:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(manager.stop_adapter(instance_name))
                    loop.close()
            except Exception as e:
                pass  # 继续删除

    # 从配置中移除
    del platforms_data[instance_name]
    with open(CONFIG_DIR / "platforms.yaml", "w", encoding="utf-8") as f:
        yaml.dump(platforms_data, f, allow_unicode=True, sort_keys=False)

    try:
        config_loader.reload()
    except Exception:
        pass

    return jsonify({"ok": True, "message": f"适配器 {instance_name} 已删除"})


# ============ API：工具测试 ============

@app.route("/api/tools/<name>", methods=["POST"])
def api_tools_run(name):
    data = request.get_json() or {}
    params = data.get("parameters", {})
    if name not in AVAILABLE_TOOLS:
        return jsonify({"error": "Unknown tool"}), 404
    result = execute_function(name, params)
    return jsonify(result)


@app.route("/api/tools")
def api_tools_list():
    registry = get_registry()
    tools = []
    for t in registry.list_tools():
        tools.append({
            "name": t.name,
            "title": t.description,
            "description": t.description,
            "fields": [
                {
                    "key": p.name,
                    "label": p.description.split("，")[0].split(",")[0],
                    "placeholder": p.description,
                    "required": p.required
                }
                for p in t.parameters
            ]
        })
    return jsonify(tools)


@app.route("/api/logs/modules")
def api_logs_modules():
    logs_list = list(LOG_QUEUE.queue)
    modules = sorted({l.get("module", "system") for l in logs_list if l.get("module")})
    if not modules:
        modules = ["system", "core", "adapter", "llm", "tools"]
    return jsonify(modules)


@app.route("/api/dashboard/chart")
def api_dashboard_chart():
    """返回系统活动图表数据（24小时）—— 当前为占位数据"""
    # TODO: 接入 MetricsStore 后返回真实时序数据
    data = [0] * 24
    return jsonify(data)


@app.route("/api/plan/event-types")
def api_plan_event_types():
    return jsonify([
        {"value": "other", "label": "Other"},
        {"value": "wake", "label": "Wake"},
        {"value": "meal", "label": "Meal"},
        {"value": "work", "label": "Work"},
        {"value": "study", "label": "Study"},
        {"value": "social", "label": "Social"},
        {"value": "entertainment", "label": "Entertainment"},
        {"value": "rest", "label": "Rest"},
        {"value": "exercise", "label": "Exercise"},
        {"value": "appointment", "label": "Appointment"},
        {"value": "task", "label": "Task"},
        {"value": "sleep", "label": "Sleep"}
    ])


# ============ API：日志中心（SSE） ============

@app.route("/api/logs/stream")
def api_logs_stream():
    def event_stream():
        while True:
            try:
                item = LOG_QUEUE.get(timeout=5)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                # Drain any additional accumulated items
                while True:
                    try:
                        item = LOG_QUEUE.get_nowait()
                        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        break
            except queue.Empty:
                yield ": keepalive\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/logs", methods=["GET", "DELETE"])
def api_logs():
    if request.method == "DELETE":
        cleared = LOG_QUEUE.qsize()
        while True:
            try:
                LOG_QUEUE.get_nowait()
            except queue.Empty:
                break
        # 也清空日志文件（轮转）
        try:
            if LOG_FILE.exists():
                LOG_FILE.write_text("", encoding="utf-8")
        except Exception:
            pass
        return jsonify({"ok": True, "cleared": cleared})

    level = request.args.get("level", "")
    module = request.args.get("module", "")
    logs = list(LOG_QUEUE.queue)

    # 内存日志不足 200 条时，从日志文件补充历史
    if len(logs) < 200 and LOG_FILE.exists():
        try:
            file_lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
            file_logs = []
            import re as _re
            for line in file_lines[-500:]:
                m = _re.match(r'\[(.+?)\]\s+\[(.+?)\]\s+\[(.+?)\]\s+(.*)', line)
                if m:
                    file_logs.append({
                        "time": m.group(1),
                        "level": m.group(2),
                        "module": m.group(3),
                        "message": m.group(4),
                    })
            seen = set()
            merged = []
            for entry in file_logs + logs:
                key = (entry.get("time", ""), entry.get("message", "")[:80])
                if key not in seen:
                    seen.add(key)
                    merged.append(entry)
            logs = merged[-200:]
        except Exception:
            pass

    if level:
        logs = [l for l in logs if l.get("level") == level]
    if module:
        logs = [l for l in logs if l.get("module") == module]
    return jsonify(logs[-200:])


# ============ API：系统管理 ============

@app.route("/api/system/reload", methods=["POST"])
def api_system_reload():
    """重载系统配置"""
    try:
        config_loader.reload()
        return jsonify({"ok": True, "message": "配置已重载"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ 认证 API ============

@app.route("/api/login", methods=["POST"])
def api_login():
    # 频率限制检查
    rate_error = _check_login_rate_limit()
    if rate_error:
        return jsonify({"ok": False, "error": rate_error}), 429

    data = request.get_json(silent=True) or {}
    import hmac
    token_val = data.get("token")
    if isinstance(token_val, str) and hmac.compare_digest(token_val, WEBUI_TOKEN):
        _record_login_attempt(success=True)
        session["webui_authed"] = True
        return jsonify({"ok": True, "redirect": "/dashboard"})

    _record_login_attempt(success=False)
    return jsonify({"ok": False, "error": "令牌错误"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("webui_authed", None)
    return jsonify({"ok": True})


# ============ 模型获取 API ============

@app.route("/api/services/<provider_name>/models")
def api_fetch_models(provider_name):
    """获取指定服务商的可用模型列表"""
    try:
        provider = config_loader.get_provider(provider_name)
        if not provider:
            return jsonify({"ok": False, "error": f"服务商 {provider_name} 不存在"}), 404
        if not provider.api_key or not provider.base_url:
            return jsonify({"ok": False, "error": "该服务商未配置 api_key 或 base_url"}), 400

        from openai import OpenAI
        client = OpenAI(api_key=provider.api_key, base_url=provider.base_url)
        models = client.models.list()
        model_list = [{"id": m.id, "owned_by": getattr(m, "owned_by", "")} for m in models]
        return jsonify({"ok": True, "models": model_list})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ 引导流程 API ============

@app.route("/api/guide/fetch_models", methods=["POST"])
def guide_fetch_models():
    """引导流程中用原始 base_url+api_key 拉取模型列表（不依赖已存配置）"""
    data = request.get_json(silent=True) or {}
    base_url = (data.get("base_url") or "").rstrip("/")
    api_key = data.get("api_key") or ""
    if not base_url or not api_key:
        return jsonify({"ok": False, "error": "缺少 base_url 或 api_key"}), 400
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        models = [m.id for m in client.models.list()]
        return jsonify({"ok": True, "models": models})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ============ 图片上传 API ============

@app.route("/api/chat/upload", methods=["POST"])
def api_chat_upload():
    """上传聊天图片到 data/temp/"""
    try:
        from core.utils.temp_manager import temp_manager
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "未找到文件"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"ok": False, "error": "文件名为空"}), 400
        image_data = file.read()
        import time
        filename = f"chat_{int(time.time()*1000)}_{file.filename}"
        saved_path = temp_manager.save_image(image_data, filename)
        return jsonify({"ok": True, "path": saved_path})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ 插件管理 API ============

@app.route("/api/plugins")
def api_plugins():
    """获取插件列表"""
    try:
        from core.plugin import PluginManager
        available = []
        for manifest in PluginManager.list_available():
            available.append({
                "id": manifest.id,
                "name": manifest.name,
                "version": manifest.version,
                "author": manifest.author,
                "description": manifest.description,
                "hooks": manifest.hooks,
                "builtin": manifest.builtin,
                "requirements": manifest.requirements,
            })
        core = get_core()
        loaded = core.plugin_manager.list_loaded() if core and core.plugin_manager else []
        return jsonify({"ok": True, "plugins": available, "loaded": loaded})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugins/<plugin_id>/toggle", methods=["POST"])
def api_plugin_toggle(plugin_id):
    """启用/禁用插件（含持久化）"""
    try:
        from core.plugin import PluginManager, save_plugin_config
        core = get_core()
        if core and core.plugin_manager:
            pm = core.plugin_manager
        else:
            pm = PluginManager()
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled", True)

        if enabled:
            success = pm.load_plugin(plugin_id)
        else:
            success = pm.unload_plugin(plugin_id)

        if success:
            save_plugin_config(config_loader._data_dir, plugin_id, enabled)
            if core and core.toolllm:
                core.toolllm.rebuild_tool_definitions()
            return jsonify({"ok": True, "message": f"插件 {plugin_id} 已{'加载' if enabled else '卸载'}"})
        else:
            return jsonify({"ok": False, "message": "操作失败"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugins/install", methods=["POST"])
def api_plugin_install():
    """安装自定义插件（.zip 上传）"""
    try:
        if 'file' not in request.files:
            return jsonify({"ok": False, "error": "请选择文件"}), 400
        file = request.files['file']
        if not file.filename or not file.filename.endswith('.zip'):
            return jsonify({"ok": False, "error": "仅支持 .zip 格式"}), 400

        from core.plugin import PluginManager, save_plugin_config

        project_root = Path(__file__).parent.parent
        custom_dir = project_root / "data" / "custom_plugins"
        custom_dir.mkdir(parents=True, exist_ok=True)

        # Unique temp file to avoid concurrent upload collisions
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", dir=str(custom_dir))
        os.close(tmp_fd)
        file.save(tmp_path)

        try:
            core = get_core()
            if core and core.plugin_manager:
                pm = core.plugin_manager
            else:
                pm = PluginManager()
            toolllm = core.toolllm if core else None
            result = pm.install_from_zip(Path(tmp_path), custom_dir, toolllm=toolllm)
        finally:
            os.unlink(tmp_path)

        if result.get("ok"):
            save_plugin_config(config_loader._data_dir, result["plugin_id"], True)
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        logger.error("Plugin install failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/plugins/<plugin_id>", methods=["DELETE"])
def api_plugin_delete(plugin_id):
    """删除自定义插件（仅限非内置插件）"""
    try:
        from core.plugin import PluginManager, remove_plugin_config

        manifest = PluginManager._manifests.get(plugin_id)
        if not manifest:
            return jsonify({"ok": False, "error": "插件不存在"}), 404
        if manifest.builtin:
            return jsonify({"ok": False, "error": "内置插件不可删除"}), 403

        core = get_core()
        if core and core.plugin_manager:
            pm = core.plugin_manager
        else:
            pm = PluginManager()

        # Find which directory the plugin lives in
        project_root = Path(__file__).parent.parent
        for search_dir in [
            project_root / "data" / "custom_plugins",
        ]:
            plugin_dir = search_dir / plugin_id
            if plugin_dir.exists():
                break
        else:
            return jsonify({"ok": False, "error": "插件目录未找到"}), 404

        pm.unload_plugin(plugin_id)
        pm._unregister_plugin(plugin_id)

        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        remove_plugin_config(config_loader._data_dir, plugin_id)

        if core and core.toolllm:
            core.toolllm.rebuild_tool_definitions()

        return jsonify({"ok": True, "message": f"插件 {plugin_id} 已删除"})
    except Exception as e:
        logger.error("Plugin delete failed: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ API：知识库管理 ============

@app.route("/api/knowledge/status")
def api_knowledge_status():
    """获取知识库系统状态"""
    try:
        from core.rag.knowledge_manager import knowledge_manager
        return jsonify(knowledge_manager.get_status())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/knowledge/<kb_name>/documents")
def api_knowledge_documents(kb_name):
    """获取知识库文档列表"""
    try:
        from core.rag.knowledge_manager import knowledge_manager
        docs = knowledge_manager.get_documents(kb_name)
        return jsonify([
            {
                "id": d.id, "kb_name": d.kb_name, "filename": d.filename,
                "file_type": d.file_type, "file_size": d.file_size,
                "chunk_count": d.chunk_count, "uploaded_at": d.uploaded_at,
                "status": d.status,
            }
            for d in docs
        ])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/knowledge/<kb_name>/upload", methods=["POST"])
def api_knowledge_upload(kb_name):
    """上传文档并自动索引"""
    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "未找到文件"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"ok": False, "error": "文件名为空"}), 400

        ext = Path(file.filename).suffix.lower()
        if ext not in {".txt", ".md", ".pdf", ".csv"}:
            return jsonify({"ok": False, "error": f"不支持的文件类型: {ext}"}), 400

        import re
        # 安全化 kb_name（仅允许字母、数字、中划线、下划线）
        safe_kb_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', kb_name)
        if safe_kb_name != kb_name:
            logger.warning("知识库名称包含不安全字符，已规范化: '%s' -> '%s'", kb_name, safe_kb_name)
            kb_name = safe_kb_name

        # 安全化文件名（剥离路径组件，防止路径穿越）
        safe_filename = Path(file.filename).name
        if safe_filename != file.filename:
            logger.warning("文件名包含路径组件，已规范化: '%s' -> '%s'", file.filename, safe_filename)

        from core.rag.knowledge_manager import knowledge_manager

        rag_docs_base = Path(config_loader._data_dir) / "rag" / "documents"
        rag_docs_dir = rag_docs_base / kb_name
        upload_id = str(uuid.uuid4())
        dest_dir = rag_docs_dir / upload_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / safe_filename

        # 验证最终路径在预期范围内（防止路径穿越）
        resolved = dest_path.resolve()
        if not str(resolved).startswith(str(rag_docs_base.resolve())):
            return jsonify({"ok": False, "error": "非法路径"}), 400

        file.save(str(dest_path))

        record = knowledge_manager.upload_document(
            kb_name, str(dest_path), safe_filename, doc_id=upload_id
        )
        return jsonify({
            "ok": True,
            "document": {
                "id": record.id, "filename": record.filename,
                "chunk_count": record.chunk_count, "status": record.status,
            },
        })
    except Exception as e:
        logger.error("知识库上传失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/knowledge/<kb_name>/rebuild", methods=["POST"])
def api_knowledge_rebuild(kb_name):
    """重建知识库索引"""
    try:
        from core.rag.knowledge_manager import knowledge_manager
        knowledge_manager.rebuild_index(kb_name)
        return jsonify({"ok": True, "message": "索引重建完成"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/knowledge/<kb_name>/test", methods=["POST"])
def api_knowledge_test(kb_name):
    """测试检索"""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "查询不能为空"}), 400
    try:
        from core.rag.knowledge_manager import knowledge_manager
        results = knowledge_manager.retrieve(query)
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/knowledge/<kb_name>/documents/<doc_id>", methods=["DELETE"])
def api_knowledge_delete_document(kb_name, doc_id):
    """删除文档"""
    try:
        from core.rag.knowledge_manager import knowledge_manager
        ok = knowledge_manager.delete_document(doc_id)
        if not ok:
            return jsonify({"ok": False, "error": "文档未找到"}), 404
        return jsonify({"ok": True, "message": "文档已删除"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ API：会话管理 ============

@app.route("/api/sessions")
def api_sessions_list():
    """获取所有活跃会话列表"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": True, "sessions": [], "persistence_enabled": False})
        session_list = core.session_manager.list_sessions()
        data = []
        for s in session_list:
            mem_count = core.session_manager.get_memory_count(s.sid)
            data.append({
                "sid": s.sid,
                "adapter": s.adapter_name,
                "type": s.session_type,
                "id": s.session_id,
                "title": s.session_title or "",
                "description": s.session_description or "",
                "timestamp": s.timestamp,
                "memory_count": mem_count,
                "enabled": s.enabled,
            })
        return jsonify({"ok": True, "sessions": data, "persistence_enabled": True})
    except Exception:
        logger.exception("获取会话列表失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/cleanup", methods=["POST"])
def api_sessions_cleanup():
    """清理过期会话"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        deleted = core.session_manager.cleanup_expired(days=7)
        return jsonify({"ok": True, "deleted": deleted})
    except Exception:
        logger.exception("清理过期会话失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/<path:sid>")
def api_session_get(sid):
    """获取指定会话详情（只读，不会创建新会话）"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        s = core.session_manager.get_session(sid)
        if not s:
            return jsonify({"ok": False, "error": "会话不存在"}), 404
        chunks = core.session_manager.get_memory_chunks(sid)
        memory = [
            {"id": c.get("id"), "user": c.get("user", ""), "assistant": c.get("assistant", "")}
            for c in chunks
        ]
        return jsonify({
            "ok": True,
            "session": {
                "sid": s.sid,
                "adapter": s.adapter_name,
                "type": s.session_type,
                "id": s.session_id,
                "title": s.session_title or "",
                "description": s.session_description or "",
                "timestamp": s.timestamp,
                "memory_count": len(memory),
                "enabled": s.enabled,
            },
            "memory": memory,
        })
    except Exception:
        logger.exception("获取会话详情失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/<path:sid>", methods=["DELETE"])
def api_session_delete(sid):
    """删除指定会话"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        core.session_manager.delete_session(sid)
        return jsonify({"ok": True})
    except Exception:
        logger.exception("删除会话失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/<path:sid>/clear", methods=["POST"])
def api_session_clear(sid):
    """清空指定会话的记忆"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        core.session_manager.clear_memory(sid)
        return jsonify({"ok": True})
    except Exception:
        logger.exception("清空会话记忆失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/<path:sid>/meta", methods=["POST"])
def api_session_meta(sid):
    """编辑会话元数据（title/description/enabled）

    类型不符返回 400，避免静默丢弃却回 ok。
    """
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        data = request.get_json(silent=True) or {}
        title = data.get("title")
        description = data.get("description")
        enabled = data.get("enabled")

        # 字段存在则必须类型正确，否则 400
        if title is not None and not isinstance(title, str):
            return jsonify({"ok": False, "error": "title 必须是字符串"}), 400
        if description is not None and not isinstance(description, str):
            return jsonify({"ok": False, "error": "description 必须是字符串"}), 400
        if enabled is not None and not isinstance(enabled, bool):
            return jsonify({"ok": False, "error": "enabled 必须是布尔值"}), 400

        core.session_manager.update_session(
            sid, title=title, description=description, enabled=enabled,
        )
        return jsonify({"ok": True})
    except Exception:
        logger.exception("更新会话元数据失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/<path:sid>/memory", methods=["POST"])
def api_session_memory_add(sid):
    """手动添加一轮记忆"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        data = request.get_json(silent=True) or {}
        user_text = (data.get("user") or "").strip()
        asst_text = (data.get("assistant") or "").strip()
        if not user_text or not asst_text:
            return jsonify({"ok": False, "error": "用户消息和 AI 回复均不能为空"}), 400
        ok = core.session_manager.append_memory(
            sid,
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": asst_text},
        )
        return jsonify({"ok": ok})
    except Exception:
        logger.exception("添加会话记忆失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/<path:sid>/memory/<int:chunk_id>", methods=["PUT"])
def api_session_memory_update(sid, chunk_id):
    """按 chunk id 编辑一轮记忆"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        data = request.get_json(silent=True) or {}
        user_text = (data.get("user") or "").strip()
        asst_text = (data.get("assistant") or "").strip()
        if not user_text or not asst_text:
            return jsonify({"ok": False, "error": "用户消息和 AI 回复均不能为空"}), 400
        ok = core.session_manager.update_memory_chunk(sid, chunk_id, user_text, asst_text)
        if not ok:
            return jsonify({"ok": False, "error": "记忆不存在或已删除"}), 404
        return jsonify({"ok": True})
    except Exception:
        logger.exception("编辑会话记忆失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.route("/api/sessions/<path:sid>/memory/<int:chunk_id>", methods=["DELETE"])
def api_session_memory_delete(sid, chunk_id):
    """按 chunk id 删除一轮记忆"""
    try:
        core = get_core()
        if not core.session_manager:
            return jsonify({"ok": False, "error": "会话管理器未启用"}), 400
        ok = core.session_manager.delete_memory_chunk(sid, chunk_id)
        if not ok:
            return jsonify({"ok": False, "error": "记忆不存在或已删除"}), 404
        return jsonify({"ok": True})
    except Exception:
        logger.exception("删除会话记忆失败")
        return jsonify({"ok": False, "error": "Internal server error"}), 500


# ============ 日志拦截（捕获 logging 与 print 输出到 LOG_QUEUE） ============

class LogQueueHandler(logging.Handler):
    """将 logging 日志记录捕获到 LOG_QUEUE，供 WebUI SSE 推送"""

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.queue = LOG_QUEUE
        # 简化格式，只取时间、级别、模块名和消息
        self.setFormatter(logging.Formatter("%(asctime)s||%(levelname)s||%(name)s||%(message)s", datefmt="%H:%M:%S"))

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """移除 ANSI 转义序列"""
        import re as _re
        return _re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)

    def emit(self, record):
        try:
            # 使用自定义格式化快速解析各部分
            formatted = self.format(record)
            parts = formatted.split("||", 3)
            time_str = parts[0] if len(parts) > 0 else datetime.now().strftime("%H:%M:%S")
            level = parts[1] if len(parts) > 1 else "INFO"
            module = parts[2] if len(parts) > 2 else "system"
            message = parts[3] if len(parts) > 3 else formatted
            # 清理 ANSI 转义码
            message = self._strip_ansi(message)

            _put_log({
                "time": time_str,
                "level": level,
                "module": module.split(".")[-1],  # 只取最后一段作为模块名
                "message": message
            })
        except Exception:
            pass


class LogInterceptor:
    """把 print 输出捕获到内存队列，供 SSE 使用"""

    def __init__(self, original):
        self.original = original
        self.buffer = ""

    def write(self, s):
        self.original.write(s)
        if s.strip():
            _put_log({
                "time": datetime.now().strftime("%H:%M:%S"),
                "level": "INFO",
                "module": "system",
                "message": s.rstrip("\n")
            })

    def flush(self):
        self.original.flush()


# 安装 LogQueueHandler 到根日志记录器（不会被 setup_logging 清除，且通过传播捕获所有 Tale.* 日志）
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)  # 确保低级别日志也能通过传播到达 handler
_log_handler = LogQueueHandler()
_log_handler.setLevel(logging.DEBUG)
_root_logger.addHandler(_log_handler)


# ============ 启动 ============

if __name__ == "__main__":
    print("=" * 50)
    print("  Tale WebUI 启动中...")
    print("  访问: http://127.0.0.1:32456")
    print("=" * 50)
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=32456, debug=debug, threaded=True)
