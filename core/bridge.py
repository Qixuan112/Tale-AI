"""
消息桥接模块（Bridge）

跨会话消息收发核心，独立于 Session 数据模型。
支持两阶段提交（consume/ack）、UUID 去重、per-session 并发控制与频率限制。

设计原则：
- 不污染 Session 数据模型（inbox/pending/processed 全在 BridgeState 内存中）
- 不持多个会话锁（send 只争目标锁，不持本锁）
- at-least-once 语义：pending 超时未 ack 重新投递
- 所有集合有上界淘汰
- 状态持久化：重启后恢复 inbox/pending/processed/rate 状态
"""

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from .utils import get_logger

logger = get_logger(__name__)


class BridgeMessage:
    """一条跨会话消息"""

    def __init__(self, from_sid: str, content: str):
        self.id = uuid.uuid4().hex[:16]
        self.from_sid = from_sid
        self.content = content[:BridgeState.MAX_CONTENT]
        self.timestamp = int(time.time())
        # 进入 pending 的时刻，移入 pending 时刷新；与 timestamp（创建时刻）独立，
        # 用于 pending 超时判定，避免老消息按创建时间被误判过期循环重投。
        self.enqueued_at = 0

    def to_dict(self) -> dict:
        return {"id": self.id, "from_sid": self.from_sid,
                "content": self.content, "timestamp": self.timestamp}

    def to_persist_dict(self) -> dict:
        """序列化为持久化字典（包含 enqueued_at）"""
        return {
            "id": self.id,
            "from_sid": self.from_sid,
            "content": self.content,
            "timestamp": self.timestamp,
            "enqueued_at": self.enqueued_at
        }

    @staticmethod
    def from_persist_dict(data: dict) -> 'BridgeMessage':
        """从持久化字典恢复"""
        msg = BridgeMessage.__new__(BridgeMessage)
        msg.id = data["id"]
        msg.from_sid = data["from_sid"]
        msg.content = data["content"]
        msg.timestamp = data["timestamp"]
        msg.enqueued_at = data.get("enqueued_at", 0)
        return msg


class BridgeState:
    """跨会话桥接状态（带持久化）

    线程安全：per-session asyncio.Lock，send 只争目标锁。
    状态持久化：inbox/pending/processed/rate 在状态变更后 debounce 写入 JSON。
    """

    MAX_INBOX = 20          # 单个 inbox 上限
    MAX_POP = 5             # 单次消费最多 5 条
    MAX_CONTENT = 500       # 消息长度上限（字符）
    MAX_PROCESSED = 1000    # 去重集合上限
    PENDING_TTL = 3600      # 去重 TTL（秒）
    PENDING_TIMEOUT = 300   # pending 超时重投（秒）
    RATE_INTERVAL = 60      # 率控时间窗口（秒）
    RATE_LIMIT = 10         # 窗口内最大发送数
    SID_IDLE_TTL = 3600     # 空闲 sid 淘汰 TTL（秒）：inbox/pending 皆空且超时则清理
    PERSIST_DEBOUNCE = 0.2  # 持久化 debounce 时间（秒）
    PROCESSED_PERSIST_DAYS = 7  # _processed 只持久化最近 N 天

    def __init__(self, persistence_file: Optional[str] = None):
        self._inbox: dict[str, list[BridgeMessage]] = {}
        self._pending: dict[str, list[BridgeMessage]] = {}
        self._processed: dict[str, list[tuple]] = {}  # [(msg_id, timestamp), ...] FIFO
        self._locks: dict[str, asyncio.Lock] = {}
        self._rate: dict[str, list[float]] = {}
        self._last_active: dict[str, float] = {}  # 每 sid 最后活跃时刻，用于空闲淘汰

        # 持久化相关
        self._persist_path: Optional[Path] = None
        self._persist_task: Optional[asyncio.Task] = None
        self._persist_dirty = False

        # 确定持久化路径
        if persistence_file:
            self._persist_path = Path(persistence_file)
        else:
            # 默认路径：data/bridge/state.json
            self._persist_path = Path("data/bridge/state.json")

        # 加载持久化状态
        self._load_state()

    def __del__(self):
        """析构时同步保存状态（最后机会）"""
        if self._persist_dirty and self._persist_path:
            try:
                # 解释器关闭时，内置函数可能已被清理为 None，显式导入确保可用
                import builtins
                import time as time_module
                import json as json_module

                # 同步保存（无法使用 async）
                cutoff = time_module.time() - (BridgeState.PROCESSED_PERSIST_DAYS * 86400)
                data = {
                    "inbox": {
                        sid: [m.to_persist_dict() for m in msgs]
                        for sid, msgs in self._inbox.items()
                    },
                    "pending": {
                        sid: [m.to_persist_dict() for m in msgs]
                        for sid, msgs in self._pending.items()
                    },
                    "processed": {
                        sid: [(mid, ts) for mid, ts in items if ts > cutoff]
                        for sid, items in self._processed.items()
                    },
                    "rate": self._rate,
                    "last_active": self._last_active
                }
                self._persist_path.parent.mkdir(parents=True, exist_ok=True)

                # 使用 builtins.open 确保函数可用
                with builtins.open(self._persist_path, 'w', encoding='utf-8') as f:
                    json_module.dump(data, f, ensure_ascii=False, indent=2)

                logger.debug("BridgeState 析构时已持久化到: %s", self._persist_path)
            except Exception:
                # 静默忽略，避免析构时异常
                pass

    async def flush(self):
        """立即刷新持久化状态（等待 debounce 任务完成）"""
        if self._persist_task and not self._persist_task.done():
            await self._persist_task
        if self._persist_dirty:
            await self._save_state()
            self._persist_dirty = False

    def _lock(self, sid: str) -> asyncio.Lock:
        return self._locks.setdefault(sid, asyncio.Lock())

    def _touch(self, sid: str):
        """刷新 sid 最后活跃时刻"""
        self._last_active[sid] = time.time()

    def _mark_dirty(self):
        """标记状态已修改，触发 debounce 持久化"""
        self._persist_dirty = True
        if self._persist_task is None or self._persist_task.done():
            self._persist_task = asyncio.create_task(self._debounce_persist())

    async def _debounce_persist(self):
        """Debounce 持久化：等待 PERSIST_DEBOUNCE 秒后写入"""
        await asyncio.sleep(BridgeState.PERSIST_DEBOUNCE)
        if self._persist_dirty:
            self._persist_dirty = False
            await self._save_state()

    def _load_state(self):
        """启动时从 JSON 文件加载状态"""
        if not self._persist_path or not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 恢复 inbox
            for sid, msgs in data.get("inbox", {}).items():
                self._inbox[sid] = [BridgeMessage.from_persist_dict(m) for m in msgs]

            # 恢复 pending - 重启后将 pending 消息重新放回 inbox（进程重启意味着之前的消费者可能已失效）
            # 这样可以确保未 ack 的消息在重启后能够被重新消费
            for sid, msgs in data.get("pending", {}).items():
                pending_msgs = [BridgeMessage.from_persist_dict(m) for m in msgs]
                # 将 pending 消息移回 inbox
                if sid not in self._inbox:
                    self._inbox[sid] = []
                self._inbox[sid].extend(pending_msgs)
                logger.info("重启后将 %d 条 pending 消息重新放回 inbox: sid=%s", len(pending_msgs), sid)

            # 恢复 _processed（过滤超过 PROCESSED_PERSIST_DAYS 的）
            cutoff = time.time() - (BridgeState.PROCESSED_PERSIST_DAYS * 86400)
            for sid, items in data.get("processed", {}).items():
                self._processed[sid] = [(mid, ts) for mid, ts in items if ts > cutoff]

            # 恢复 _rate
            for sid, ts_list in data.get("rate", {}).items():
                self._rate[sid] = ts_list

            # 恢复 _last_active
            for sid, ts in data.get("last_active", {}).items():
                self._last_active[sid] = ts

            logger.info("BridgeState 已从持久化文件加载: %s", self._persist_path)

        except json.JSONDecodeError as e:
            logger.warning("BridgeState 持久化文件损坏，从空状态启动: %s (error: %s)",
                          self._persist_path, e)
        except Exception as e:
            logger.error("加载 BridgeState 持久化文件失败: %s (error: %s)",
                        self._persist_path, e)

    async def _save_state(self):
        """将当前状态保存到 JSON 文件（异步非阻塞）"""
        if not self._persist_path:
            return

        try:
            # 准备序列化数据（过滤过期 _processed）
            cutoff = time.time() - (BridgeState.PROCESSED_PERSIST_DAYS * 86400)

            data = {
                "inbox": {
                    sid: [m.to_persist_dict() for m in msgs]
                    for sid, msgs in self._inbox.items()
                },
                "pending": {
                    sid: [m.to_persist_dict() for m in msgs]
                    for sid, msgs in self._pending.items()
                },
                "processed": {
                    sid: [(mid, ts) for mid, ts in items if ts > cutoff]
                    for sid, items in self._processed.items()
                },
                "rate": self._rate,
                "last_active": self._last_active
            }

            # 确保目录存在
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入临时文件，然后原子替换（避免写入中途崩溃导致损坏）
            temp_path = self._persist_path.with_suffix('.tmp')

            # 使用 asyncio 在线程池中执行 IO（避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_json, temp_path, data)
            await loop.run_in_executor(None, temp_path.replace, self._persist_path)

            logger.debug("BridgeState 已持久化到: %s", self._persist_path)

        except Exception as e:
            logger.error("保存 BridgeState 持久化文件失败: %s (error: %s)",
                        self._persist_path, e)

    @staticmethod
    def _write_json(path: Path, data: dict):
        """同步写入 JSON 文件（在线程池中执行）"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _evict_idle(self):
        """空闲 sid 淘汰：inbox 与 pending 皆空、超过 SID_IDLE_TTL 未活跃，
        且锁未被持有/争用时，从全部五个 dict 与锁表中移除该 sid，
        维持"所有集合有上界"的不变式。
        """
        cutoff = time.time() - BridgeState.SID_IDLE_TTL
        # 快照键，避免遍历中修改。并集 _locks 以回收「只创建了锁却没记录活跃时刻」
        # 的孤儿锁（缺失 _last_active 视为 0，即已空闲）。
        evicted = False
        for sid in list(set(self._last_active.keys()) | set(self._locks.keys())):
            if self._last_active.get(sid, 0) > cutoff:
                continue
            if self._inbox.get(sid) or self._pending.get(sid):
                continue
            lock = self._locks.get(sid)
            # 仅淘汰空闲（锁未被持有/无人等待）的 sid，避免清理正在使用的锁
            if lock is not None and lock.locked():
                continue
            self._inbox.pop(sid, None)
            self._pending.pop(sid, None)
            self._processed.pop(sid, None)
            self._rate.pop(sid, None)
            self._locks.pop(sid, None)
            self._last_active.pop(sid, None)
            logger.debug("跨会话空闲 sid 淘汰: sid=%s", sid)
            evicted = True

        # 触发持久化
        if evicted:
            self._mark_dirty()

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
        """频率限制：窗口内不超过上限

        best-effort：_rate 无独立锁，并发下可能短暂超限，
        但对限流目的可接受（防止 AI 异常高频刷屏，非精确计量）。
        """
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
        # 按 timestamp 过滤超 TTL 的
        items = [(mid, ts) for mid, ts in items if ts > ttl_cutoff]
        if len(items) > BridgeState.MAX_PROCESSED:
            items = items[-BridgeState.MAX_PROCESSED:]
        self._processed[sid] = items

    def _is_processed(self, sid: str, msg_id: str) -> bool:
        for mid, _ts in self._processed.get(sid, []):
            if mid == msg_id:
                return True
        return False

    def _mark_processed(self, sid: str, msg_id: str):
        self._prune_processed(sid)
        if sid not in self._processed:
            self._processed[sid] = []
        self._processed[sid].append((msg_id, time.time()))

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
            self._touch(to_sid)

        # 触发持久化
        self._mark_dirty()

        # 空闲 sid 淘汰（不持锁，仅清理已空且超时的 sid）
        self._evict_idle()

        logger.info("跨会话消息已发送: %s → %s (id=%s, len=%d)",
                    from_sid, to_sid, msg.id, len(text))
        return msg.id

    async def add_system_message(self, sid: str, text: str) -> str:
        """向指定会话 inbox 追加一条系统消息（不做权限/率控校验）

        用于系统侧主动注入消息（from_sid 形如 "system"），复用 send() 的
        BridgeMessage 构造与 inbox 追加逻辑，但绕过 _check_permission/_check_rate。

        Returns:
            消息 id
        """
        # 构造消息（自动 500 字符截断）
        text = text[:BridgeState.MAX_CONTENT]
        msg = BridgeMessage("system", text)

        # 写入目标 inbox（持目标锁）
        async with self._lock(sid):
            if sid not in self._inbox:
                self._inbox[sid] = []
            inbox = self._inbox[sid]
            if len(inbox) >= BridgeState.MAX_INBOX:
                dropped = inbox.pop(0)
                logger.warning("跨会话 inbox 溢出丢弃: to=%s, dropped_id=%s, from=%s",
                               sid, dropped.id, dropped.from_sid)
            inbox.append(msg)
            self._touch(sid)

        # 触发持久化
        self._mark_dirty()

        logger.info("系统消息已注入: → %s (id=%s, len=%d)", sid, msg.id, len(text))
        return msg.id

    async def consume(self, sid: str) -> list[dict]:
        """消费目标会话的待处理跨会话消息

        两阶段：移入 pending，ack 后才真正删除。
        超时未 ack 重新入队。

        Returns:
            消息 dict 列表 [{"id":..., "from_sid":..., "content":..., "timestamp":...}]
        """
        async with self._lock(sid):
            self._touch(sid)
            # 1. 检查 pending 超时消息 → 重新入队
            #    超时以 enqueued_at（进入 pending 时刻）为准，而非 timestamp（创建时刻），
            #    否则老消息会在下一次 consume 立即被判定过期，无限循环重投。
            now = time.time()
            cutoff = now - BridgeState.PENDING_TIMEOUT
            expired = [m for m in self._pending.get(sid, [])
                       if m.enqueued_at < cutoff]
            if expired:
                self._pending[sid] = [m for m in self._pending.get(sid, [])
                                      if m.enqueued_at >= cutoff]
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

            # 4. 移入 pending，记录进入 pending 的时刻供超时判定
            if sid not in self._pending:
                self._pending[sid] = []
            enqueued_at = time.time()
            for m in filtered:
                m.enqueued_at = enqueued_at
            self._pending[sid].extend(filtered)

            # 触发持久化
            if filtered or expired:
                self._mark_dirty()

            return [m.to_dict() for m in filtered]

    async def ack(self, sid: str, message_ids: list[str]):
        """确认消息已处理完成

        从 pending 移除，加入去重集合。
        不存在的 id 静默忽略（幂等）。
        """
        async with self._lock(sid):
            self._touch(sid)
            id_set = set(message_ids)
            pending = self._pending.get(sid, [])
            keep = [m for m in pending if m.id not in id_set]
            removed_count = len(pending) - len(keep)
            self._pending[sid] = keep
            for mid in message_ids:
                self._mark_processed(sid, mid)
            if removed_count:
                logger.debug("跨会话 ack: sid=%s, count=%d", sid, removed_count)
                # 触发持久化
                self._mark_dirty()

    async def format_for_prompt(self, sid: str) -> str:
        """格式化本会话的 inbox 消息为 LLM prompt 文本（加锁读取）"""
        async with self._lock(sid):
            self._touch(sid)
            msgs = list(self._inbox.get(sid, []))
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
        # 快照键，避免并发修改时 RuntimeError
        all_sids = set(self._inbox.keys()) | set(self._pending.keys())
        result = []
        for other_sid in all_sids:
            if other_sid.startswith(prefix) and other_sid != sid:
                if other_sid not in result:
                    result.append(other_sid)
        return result[:5]  # 最多 5 个
