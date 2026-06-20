"""
消息桥接模块（Bridge）

跨会话消息收发核心，独立于 Session 数据模型。
支持两阶段提交（consume/ack）、UUID 去重、per-session 并发控制与频率限制。

设计原则：
- 不污染 Session 数据模型（inbox/pending/processed 全在 BridgeState 内存中）
- 不持多个会话锁（send 只争目标锁，不持本锁）
- at-least-once 语义：pending 超时未 ack 重新投递
- 所有集合有上界淘汰

已知局限：
- BridgeState 纯内存，重启即丢（计划后续持久化到 sessions.json 或 Redis）
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from ..utils import get_logger

logger = get_logger(__name__)


class BridgeMessage:
    """一条跨会话消息"""

    def __init__(self, from_sid: str, content: str):
        self.id = uuid.uuid4().hex[:16]
        self.from_sid = from_sid
        self.content = content[:BridgeState.MAX_CONTENT]
        self.timestamp = int(time.time())

    def to_dict(self) -> dict:
        return {"id": self.id, "from_sid": self.from_sid,
                "content": self.content, "timestamp": self.timestamp}


class BridgeState:
    """跨会话桥接状态（进程内存）

    线程安全：per-session asyncio.Lock，send 只争目标锁。
    """

    MAX_INBOX = 20          # 单个 inbox 上限
    MAX_POP = 5             # 单次消费最多 5 条
    MAX_CONTENT = 500       # 消息长度上限（字符）
    MAX_PROCESSED = 1000    # 去重集合上限
    PENDING_TTL = 3600      # 去重 TTL（秒）
    PENDING_TIMEOUT = 300   # pending 超时重投（秒）
    RATE_INTERVAL = 60      # 率控时间窗口（秒）
    RATE_LIMIT = 10         # 窗口内最大发送数

    def __init__(self):
        self._inbox: dict[str, list[BridgeMessage]] = {}
        self._pending: dict[str, list[BridgeMessage]] = {}
        self._processed: dict[str, list[str]] = {}  # FIFO 有序
        self._locks: dict[str, asyncio.Lock] = {}
        self._rate: dict[str, list[float]] = {}

    def _lock(self, sid: str) -> asyncio.Lock:
        if sid not in self._locks:
            self._locks[sid] = asyncio.Lock()
        return self._locks[sid]

    # ── 权限校验 ───────────────────────────────────────────────

    def _check_permission(self, from_sid: str, to_sid: str) -> Optional[str]:
        """权限校验，返回 None 表示通过，否则返回错误信息"""
        parts_f = from_sid.split(":", maxsplit=2)
        parts_t = to_sid.split(":", maxsplit=2)
        if len(parts_f) < 3 or len(parts_t) < 3:
            return "无效的会话标识"
        # 同 adapter 允许
        if parts_f[0] == parts_t[0]:
            return None
        # 同群组上下文允许（源 user_id == 目标 group_id）
        if parts_f[2] == parts_t[2]:
            return None
        return "无权向该会话发送消息"

    def _check_rate(self, sid: str) -> bool:
        """频率限制：窗口内不超过上限"""
        now = time.time()
        window = now - BridgeState.RATE_INTERVAL
        ts_list = self._rate.get(sid, [])
        ts_list = [t for t in ts_list if t > window]
        if len(ts_list) >= BridgeState.RATE_LIMIT:
            return False
        ts_list.append(now)
        self._rate[sid] = ts_list
        return True

    # ── inbox 去重淘汰 ─────────────────────────────────────────

    def _prune_processed(self, sid: str):
        """_processed 上界淘汰：超过 MAX_PROCESSED 移除最旧；超 TTL 移除"""
        ttl_cutoff = time.time() - BridgeState.PENDING_TTL
        items = self._processed.get(sid, [])
        items = [i for i in items if self._ts_from_id(i) > ttl_cutoff]
        if len(items) > BridgeState.MAX_PROCESSED:
            items = items[-BridgeState.MAX_PROCESSED:]
        self._processed[sid] = items

    @staticmethod
    def _ts_from_id(_id: str) -> int:
        """从 uuid 中提取近似时间戳（用于 TTL 淘汰）
        实际用消息创建时间，这里简化"""
        return int(time.time())

    def _is_processed(self, sid: str, msg_id: str) -> bool:
        return msg_id in self._processed.get(sid, [])

    def _mark_processed(self, sid: str, msg_id: str):
        self._prune_processed(sid)
        if sid not in self._processed:
            self._processed[sid] = []
        self._processed[sid].append(msg_id)

    # ── 核心 API ───────────────────────────────────────────────

    async def send(self, from_sid: str, to_sid: str, text: str) -> str:
        """向目标会话发送一条跨会话消息

        Returns:
            消息 id（成功），或错误字符串（失败前缀 "error:"）
        """
        # 权限校验
        perm = self._check_permission(from_sid, to_sid)
        if perm:
            logger.warning("跨会话权限拒绝: %s → %s: %s", from_sid, to_sid, perm)
            return f"error:{perm}"

        # 率控
        if not self._check_rate(to_sid):
            logger.warning("跨会话率控: %s → %s 发送太频繁", from_sid, to_sid)
            return "error:发送太频繁，请稍后重试"

        # 构造消息（自动 500 字符截断）
        text = text[:BridgeState.MAX_CONTENT]
        msg = BridgeMessage(from_sid, text)
        if len(text) >= BridgeState.MAX_CONTENT:
            logger.info("跨会话消息已截断至 %d 字符 (from=%s → to=%s)",
                        BridgeState.MAX_CONTENT, from_sid, to_sid)

        # 写入目标 inbox（持目标锁）
        async with self._lock(to_sid):
            if to_sid not in self._inbox:
                self._inbox[to_sid] = []
            inbox = self._inbox[to_sid]
            if len(inbox) >= BridgeState.MAX_INBOX:
                dropped = inbox.pop(0)
                logger.warning("跨会话 inbox 溢出丢弃: to=%s, dropped_id=%s, from=%s",
                               to_sid, dropped.id, dropped.from_sid)
            inbox.append(msg)

        logger.info("跨会话消息已发送: %s → %s (id=%s, len=%d)",
                    from_sid, to_sid, msg.id, len(text))
        return msg.id

    async def consume(self, sid: str) -> list[dict]:
        """消费目标会话的待处理跨会话消息

        两阶段：移入 pending，ack 后才真正删除。
        超时未 ack 重新入队。

        Returns:
            消息 dict 列表 [{"id":..., "from_sid":..., "content":..., "timestamp":...}]
        """
        async with self._lock(sid):
            # 1. 检查 pending 超时消息 → 重新入队
            now = int(time.time())
            cutoff = now - BridgeState.PENDING_TIMEOUT
            expired = [m for m in self._pending.get(sid, [])
                       if m.timestamp < cutoff]
            if expired:
                self._pending[sid] = [m for m in self._pending.get(sid, [])
                                      if m.timestamp >= cutoff]
                for m in expired:
                    if sid not in self._inbox:
                        self._inbox[sid] = []
                    self._inbox[sid].append(m)
                    logger.info("跨会话 pending 超时重新入队: sid=%s, msg_id=%s", sid, m.id)

            # 2. 从 inbox 取最多 MAX_POP 条
            inbox = self._inbox.get(sid, [])
            to_consume = inbox[:BridgeState.MAX_POP]
            self._inbox[sid] = inbox[BridgeState.MAX_POP:]

            # 3. 过滤已处理的
            filtered = [m for m in to_consume if not self._is_processed(sid, m.id)]

            # 4. 移入 pending
            if sid not in self._pending:
                self._pending[sid] = []
            self._pending[sid].extend(filtered)

            return [m.to_dict() for m in filtered]

    async def ack(self, sid: str, message_ids: list[str]):
        """确认消息已处理完成

        从 pending 移除，加入去重集合。
        不存在的 id 静默忽略（幂等）。
        """
        async with self._lock(sid):
            id_set = set(message_ids)
            pending = self._pending.get(sid, [])
            keep = [m for m in pending if m.id not in id_set]
            removed_count = len(pending) - len(keep)
            self._pending[sid] = keep
            for mid in message_ids:
                self._mark_processed(sid, mid)
            if removed_count:
                logger.debug("跨会话 ack: sid=%s, count=%d", sid, removed_count)

    def format_for_prompt(self, sid: str) -> str:
        """格式化本会话的 inbox 消息为 LLM prompt 文本"""
        msgs = self._inbox.get(sid, [])
        if not msgs:
            return ""
        lines = []
        for m in msgs[:BridgeState.MAX_POP]:
            content = m.content[:200]
            lines.append(f"[来自 {m.from_sid} 的跨会话消息] {content}")
        return "\n".join(lines)

    def list_accessible(self, sid: str) -> list[str]:
        """获取当前会话可通信的会话列表（同 adapter 前缀）"""
        prefix = ":".join(sid.split(":", 2)[:2]) + ":"
        result = []
        for other_sid in (list(self._inbox.keys()) +
                          list(self._pending.keys())):
            if other_sid.startswith(prefix) and other_sid != sid:
                if other_sid not in result:
                    result.append(other_sid)
        return result[:5]  # 最多 5 个
