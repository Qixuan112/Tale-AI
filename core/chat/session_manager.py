"""会话管理器

将会话历史持久化到 JSON 文件，支持自动轮转、过期清理。
参考 KiraAI core/chat/session_manager.py 设计，精简适配 Tale-AI 架构。

线程安全：WebUI 与 bot 同进程共享，所有公开方法通过单一全局 RLock 串行化，
持久化用唯一临时文件 + os.replace 原子替换。
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from ..utils import get_logger
from .session import Session

logger = get_logger(__name__)


class SessionManager:
    """会话管理器

    管理会话元数据和消息历史，持久化到 data/sessions/sessions.json。
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

        # {sid: {"title":..., "description":..., "timestamp":..., "memory":[{id, user, assistant}], "enabled":...}}
        self._data: dict[str, dict] = {}
        # 单一全局锁，串行化所有读写，避免遍历/序列化中途字典变更
        self._lock = threading.RLock()
        # chunk id 递增计数器，进程内单调递增
        self._next_chunk_id = 1

        self._load()

    # ── 内部方法 ───────────────────────────────────────────────

    def _load(self):
        """从 JSON 文件加载数据"""
        with self._lock:
            if self._file_path.exists():
                try:
                    with open(self._file_path, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                    # 先迁移旧格式（[[user, asst], ...] → [{id, user, asst}]），
                    # 迁移后所有 chunk 都是 dict，再算 max_id 才安全。
                    self._migrate_chunks()
                    # 推进 chunk id 计数器，避免与已有 id 冲突
                    max_id = 0
                    for d in self._data.values():
                        for chunk in d.get("memory", []):
                            if isinstance(chunk, dict):
                                cid = chunk.get("id", 0)
                                if isinstance(cid, int) and cid > max_id:
                                    max_id = cid
                    self._next_chunk_id = max_id + 1
                    logger.info("会话数据已加载 (%d 个会话)", len(self._data))
                except Exception as e:
                    # 加载失败不清空盘上数据：保留空内存态，但绝不覆盖原文件，
                    # 避免损坏/格式异常导致老用户会话被误删。
                    logger.error("加载会话数据失败: %s，保留磁盘文件但本次使用空数据", e)
                    self._data = {}
            else:
                self._data = {}

    def _migrate_chunks(self):
        """兼容旧格式：将 [[user, assistant], ...] 迁移为 [{id, user, assistant}]"""
        for sid, d in self._data.items():
            mem = d.get("memory", [])
            if mem and isinstance(mem[0], list):
                new_mem = []
                for chunk in mem:
                    user_msg = chunk[0] if len(chunk) > 0 else {"role": "user", "content": ""}
                    asst_msg = chunk[1] if len(chunk) > 1 else {"role": "assistant", "content": ""}
                    new_mem.append({
                        "id": self._alloc_chunk_id(),
                        "user": user_msg.get("content", ""),
                        "assistant": asst_msg.get("content", ""),
                    })
                d["memory"] = new_mem

    def _alloc_chunk_id(self) -> int:
        """分配一个新的递增 chunk id（须持锁调用）"""
        cid = self._next_chunk_id
        self._next_chunk_id += 1
        return cid

    def _save(self):
        """原子写入：用唯一临时文件 + os.replace 替换（须持锁调用）"""
        try:
            fd, tmp = tempfile.mkstemp(
                prefix=".sessions_", suffix=".tmp", dir=str(self._data_dir)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self._file_path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error("保存会话数据失败: %s", e)

    def _ensure_session(self, sid: str) -> dict:
        """确保 sid 在 _data 中存在，返回其字典（须持锁调用）"""
        if sid not in self._data:
            self._data[sid] = {
                "title": "",
                "description": "",
                "timestamp": 0,
                "memory": [],
                "enabled": True,
            }
        d = self._data[sid]
        # 兼容旧数据缺少 enabled 字段
        if "enabled" not in d:
            d["enabled"] = True
        return d

    def _get_max_memory(self, session_type: str) -> int:
        return self._max_memory.get(session_type, 50)

    def _to_session(self, sid: str, d: dict) -> Session:
        """从内部 dict 构造 Session 对象（须持锁调用）"""
        s = Session.from_sid(sid)
        s.session_title = d.get("title", "")
        s.session_description = d.get("description", "")
        s.timestamp = d.get("timestamp", 0)
        s.enabled = d.get("enabled", True)
        return s

    # ── 公开 API ───────────────────────────────────────────────

    def get_or_create(self, sid: str) -> Session:
        """获取或创建会话元数据"""
        with self._lock:
            d = self._ensure_session(sid)
            return self._to_session(sid, d)

    def get_session(self, sid: str) -> Optional[Session]:
        """只读获取会话元数据，不存在返回 None（O(1)，不创建）"""
        with self._lock:
            d = self._data.get(sid)
            if d is None:
                return None
            return self._to_session(sid, d)

    def update_session(self, sid: str, title: str = None, description: str = None, enabled: bool = None):
        """更新会话元数据

        仅修改元数据，**不刷新 timestamp**（避免禁用操作给过期会话续命）。
        timestamp 只在 memory 真正追加对话时更新。

        Args:
            title: 会话标题（None 表示不修改）
            description: 会话描述（None 表示不修改）
            enabled: 是否启用（None 表示不修改）。禁用的会话不加载历史上下文
        """
        with self._lock:
            d = self._ensure_session(sid)
            if title is not None:
                d["title"] = title
            if description is not None:
                d["description"] = description
            if enabled is not None:
                d["enabled"] = bool(enabled)
            self._save()

    def get_memory(self, sid: str) -> list[dict]:
        """获取会话历史消息列表（展平后的 [{role, content}, ...]）

        只读，不创建会话；sid 不存在返回空列表。
        """
        with self._lock:
            d = self._data.get(sid)
            if d is None:
                return []
            messages = []
            for chunk in d.get("memory", []):
                user_text = chunk.get("user", "")
                asst_text = chunk.get("assistant", "")
                if user_text:
                    messages.append({"role": "user", "content": user_text})
                if asst_text:
                    messages.append({"role": "assistant", "content": asst_text})
            return messages

    def get_memory_count(self, sid: str) -> int:
        """获取会话记忆轮数（只读，不创建会话）"""
        with self._lock:
            d = self._data.get(sid)
            return len(d.get("memory", [])) if d else 0

    def append_memory(self, sid: str, user_msg: dict, asst_msg: dict) -> bool:
        """追加一轮对话（user + assistant）

        只有当 user_msg 和 asst_msg 均非空时才写入，防止半条记录。
        追加时刷新 timestamp（标记会话活跃）。

        Returns:
            是否成功写入
        """
        if not user_msg or not user_msg.get("content"):
            return False
        if not asst_msg or not asst_msg.get("content"):
            return False

        session_type = sid.split(":", maxsplit=2)[1] if ":" in sid else "gm"
        max_mem = self._get_max_memory(session_type)

        with self._lock:
            d = self._ensure_session(sid)
            d["timestamp"] = int(time.time())
            d["memory"].append({
                "id": self._alloc_chunk_id(),
                "user": user_msg.get("content", ""),
                "assistant": asst_msg.get("content", ""),
            })
            if len(d["memory"]) > max_mem:
                d["memory"] = d["memory"][-max_mem:]
            self._save()

        logger.debug("记忆已更新 [%s] (%d 轮)", sid, len(d["memory"]))
        return True

    def clear_memory(self, sid: str):
        """清空指定会话的记忆（只读查找，不创建会话）"""
        with self._lock:
            d = self._data.get(sid)
            if d is None:
                return
            d["memory"] = []
            self._save()
        logger.info("记忆已清空 [%s]", sid)

    def list_sessions(self) -> list[Session]:
        """列出所有活跃会话"""
        with self._lock:
            return [self._to_session(sid, d) for sid, d in self._data.items()]

    # ── 单条记忆（chunk）操作 ──────────────────────────────────

    def get_memory_chunks(self, sid: str) -> list[dict]:
        """获取记忆 chunk 列表，每个含 {id, user, assistant}（只读，不创建）"""
        with self._lock:
            d = self._data.get(sid)
            if d is None:
                return []
            return [
                {"id": c.get("id"), "user": c.get("user", ""), "assistant": c.get("assistant", "")}
                for c in d.get("memory", [])
            ]

    def update_memory_chunk(self, sid: str, chunk_id: int, user_text: str, asst_text: str) -> bool:
        """按 chunk id 修改一轮记忆（id 稳定，不受 append 裁剪影响）"""
        if not user_text or not asst_text:
            return False
        with self._lock:
            d = self._data.get(sid)
            if d is None:
                return False
            for c in d.get("memory", []):
                if c.get("id") == chunk_id:
                    c["user"] = user_text
                    c["assistant"] = asst_text
                    self._save()
                    return True
            return False

    def delete_memory_chunk(self, sid: str, chunk_id: int) -> bool:
        """按 chunk id 删除一轮记忆"""
        with self._lock:
            d = self._data.get(sid)
            if d is None:
                return False
            mem = d.get("memory", [])
            for i, c in enumerate(mem):
                if c.get("id") == chunk_id:
                    mem.pop(i)
                    self._save()
                    return True
            return False

    def delete_session(self, sid: str):
        """删除会话"""
        with self._lock:
            self._data.pop(sid, None)
            self._save()
        logger.info("会话已删除 [%s]", sid)

    def cleanup_expired(self, days: int = 7) -> int:
        """删除超过指定天数未活跃的会话

        建议在初始化时调用一次，后续每小时调用一次。
        timestamp 只在对话追加时刷新，元数据编辑不会续命。

        Returns:
            删除的会话数
        """
        cutoff = int(time.time()) - days * 86400
        with self._lock:
            expired = [sid for sid, d in self._data.items()
                       if (d.get("timestamp") or 0) < cutoff]
            if not expired:
                logger.debug("过期会话清理: 无过期会话")
                return 0
            for sid in expired:
                self._data.pop(sid, None)
            self._save()
        logger.info("过期会话清理: 删除了 %d 个超过 %d 天的会话 (%s)",
                    len(expired), days, ", ".join(expired))
        return len(expired)
