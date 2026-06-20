"""会话管理器

将会话历史持久化到 JSON 文件，支持自动轮转、过期清理。
参考 KiraAI core/chat/session_manager.py 设计，精简适配 Tale-AI 架构。
"""

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..utils import get_logger
from .session import Session

logger = get_logger(__name__)


class SessionManager:
    """会话管理器

    管理会话元数据和消息历史，持久化到 data/sessions/sessions.json。
    线程安全（per-session 锁），写入使用原子替换防止崩溃损坏。
    """

    def __init__(self, data_dir: str = "data/sessions", max_memory_gm: int = 30, max_memory_dm: int = 80):
        """
        Args:
            data_dir: 会话数据目录，默认 data/sessions
            max_memory_gm: 群聊最大记忆轮数
            max_memory_dm: 私聊最大记忆轮数
        """
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = self._data_dir / "sessions.json"

        self._max_memory = {"gm": max_memory_gm, "dm": max_memory_dm}

        # {sid: {"title": ..., "description": ..., "timestamp": ..., "memory": [[...], ...]}}
        self._data: dict[str, dict] = {}
        # per-session 锁，避免全局阻塞
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

        self._load()

    # ── 内部方法 ───────────────────────────────────────────────

    def _get_lock(self, sid: str) -> threading.Lock:
        with self._global_lock:
            if sid not in self._locks:
                self._locks[sid] = threading.Lock()
            return self._locks[sid]

    def _remove_lock(self, sid: str):
        with self._global_lock:
            self._locks.pop(sid, None)

    def _file_path_tmp(self) -> str:
        """返回临时文件路径，用于原子写入"""
        return str(self._file_path) + ".tmp"

    def _load(self):
        """从 JSON 文件加载数据"""
        if self._file_path.exists():
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info("会话数据已加载 (%d 个会话)", len(self._data))
            except Exception as e:
                logger.error("加载会话数据失败: %s，使用空数据", e)
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        """原子写入：先写临时文件，再 os.replace 替换"""
        try:
            tmp = self._file_path_tmp()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._file_path)
        except Exception as e:
            logger.error("保存会话数据失败: %s", e)

    def _ensure_session(self, sid: str) -> dict:
        """确保 sid 在 _data 中存在，返回其字典"""
        if sid not in self._data:
            self._data[sid] = {
                "title": "",
                "description": "",
                "timestamp": 0,
                "memory": [],
            }
        return self._data[sid]

    def _get_max_memory(self, session_type: str) -> int:
        return self._max_memory.get(session_type, 50)

    # ── 公开 API ───────────────────────────────────────────────

    def get_or_create(self, sid: str) -> Session:
        """获取或创建会话元数据"""
        s = Session.from_sid(sid)
        lock = self._get_lock(sid)
        with lock:
            self._ensure_session(sid)
            d = self._data[sid]
            s.session_title = d.get("title", "")
            s.session_description = d.get("description", "")
            s.timestamp = d.get("timestamp", 0)
            s.enabled = d.get("enabled", True)
        return s

    def update_session(self, sid: str, title: str = None, description: str = None, enabled: bool = None):
        """更新会话元数据

        Args:
            title: 会话标题（None 表示不修改）
            description: 会话描述（None 表示不修改）
            enabled: 是否启用（None 表示不修改）。禁用的会话不加载历史上下文
        """
        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            if title is not None:
                d["title"] = title
            if description is not None:
                d["description"] = description
            if enabled is not None:
                d["enabled"] = bool(enabled)
            d["timestamp"] = int(time.time())
            self._save()

    def get_memory(self, sid: str) -> list[dict]:
        """获取会话历史消息列表（展平后的 [{role, content}, ...]）"""
        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            mem_list = d.get("memory", [])
            messages = []
            for chunk in mem_list:
                for msg in chunk:
                    messages.append(msg)
            return messages

    def get_memory_count(self, sid: str) -> int:
        """获取会话记忆轮数（无需展平，性能优于 get_memory + len）"""
        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            return len(d.get("memory", []))

    def append_memory(self, sid: str, user_msg: dict, asst_msg: dict) -> bool:
        """追加一轮对话（user + assistant）

        只有当 user_msg 和 asst_msg 均非空时才写入，防止半条记录。

        Returns:
            是否成功写入
        """
        if not user_msg or not user_msg.get("content"):
            return False
        if not asst_msg or not asst_msg.get("content"):
            return False

        session_type = sid.split(":", maxsplit=2)[1] if ":" in sid else "gm"
        max_mem = self._get_max_memory(session_type)
        new_chunk = [user_msg, asst_msg]

        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            d["timestamp"] = int(time.time())
            d["memory"].append(new_chunk)
            # 超出限制时删除最旧的 chunk
            if len(d["memory"]) > max_mem:
                d["memory"] = d["memory"][-max_mem:]
            self._save()

        logger.debug("记忆已更新 [%s] (%d 轮)", sid, len(d["memory"]))
        return True

    def clear_memory(self, sid: str):
        """清空指定会话的记忆"""
        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            d["memory"] = []
            self._save()
        logger.info("记忆已清空 [%s]", sid)

    def list_sessions(self) -> list[Session]:
        """列出所有活跃会话"""
        result = []
        for sid in self._data:
            try:
                s = Session.from_sid(sid)
                d = self._data[sid]
                s.session_title = d.get("title", "")
                s.session_description = d.get("description", "")
                s.timestamp = d.get("timestamp", 0)
                s.enabled = d.get("enabled", True)
                result.append(s)
            except ValueError:
                continue
        return result

    # ── 单条记忆（chunk）操作 ──────────────────────────────────

    def get_memory_chunks(self, sid: str) -> list[list[dict]]:
        """获取原始记忆 chunk 列表（每轮一个 [user, assistant]）"""
        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            return [list(chunk) for chunk in d.get("memory", [])]

    def add_memory_chunk(self, sid: str, user_msg: dict, asst_msg: dict) -> bool:
        """手动追加一轮记忆（供 WebUI 使用）

        与 append_memory 区别：append 由 AI 对话自动调用，add 由用户手动添加。
        两者均要求 user/asst 非空。
        """
        return self.append_memory(sid, user_msg, asst_msg)

    def update_memory_chunk(self, sid: str, index: int, user_msg: dict, asst_msg: dict) -> bool:
        """修改第 index 轮记忆"""
        if not user_msg or not user_msg.get("content"):
            return False
        if not asst_msg or not asst_msg.get("content"):
            return False
        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            mem = d.get("memory", [])
            if index < 0 or index >= len(mem):
                return False
            mem[index] = [user_msg, asst_msg]
            d["timestamp"] = int(time.time())
            self._save()
        return True

    def delete_memory_chunk(self, sid: str, index: int) -> bool:
        """删除第 index 轮记忆"""
        lock = self._get_lock(sid)
        with lock:
            d = self._ensure_session(sid)
            mem = d.get("memory", [])
            if index < 0 or index >= len(mem):
                return False
            mem.pop(index)
            d["timestamp"] = int(time.time())
            self._save()
        return True

    def delete_session(self, sid: str):
        """删除会话（含记忆和锁）"""
        lock = self._get_lock(sid)
        with lock:
            self._data.pop(sid, None)
            self._save()
        self._remove_lock(sid)
        logger.info("会话已删除 [%s]", sid)

    def cleanup_expired(self, days: int = 7):
        """删除超过指定天数未活跃的会话

        建议在初始化时调用一次，后续每小时调用一次。
        同步清理对应的 per-session 锁。
        """
        cutoff = int(time.time()) - days * 86400
        expired = [sid for sid, d in self._data.items()
                   if (d.get("timestamp") or 0) < cutoff]
        if not expired:
            logger.debug("过期会话清理: 无过期会话")
            return

        with self._global_lock:
            for sid in expired:
                self._data.pop(sid, None)
                self._locks.pop(sid, None)
            self._save()

        logger.info("过期会话清理: 删除了 %d 个超过 %d 天的会话 (%s)",
                     len(expired), days, ", ".join(expired))
