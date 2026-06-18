from __future__ import annotations

import asyncio
import os
import random
import uuid
from collections import deque
from datetime import datetime
from typing import Optional

from core.adapter.base import BaseAdapter
from core.adapter.event import (
    EventType,
    MessageContent,
    PlatformEvent,
    PlatformType,
    SenderInfo,
)
from core.utils.logger import get_logger

from core.adapter.src.wechat_pc.wechat_client import WeChatClient, WeChatMessage, WindowLostError

logger = get_logger("adapter.wechat_pc")


class WeChatPCAdapter(BaseAdapter):
    """基于 wxauto 的微信 PC 客户端适配器（Windows 限定）

    通过 UIA 自动化控制微信窗口，实现消息的收发，并可选支持朋友圈轮询。
    """

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WECHAT_PC

    def __init__(self, config, event_callback=None):
        super().__init__(config, event_callback)
        # 聊天消息配置
        self.poll_interval: float = self.get_config("poll_interval", 2.0)
        self.language: str = self.get_config("language", "cn")
        self.save_pic: bool = self.get_config("save_pic", False)
        self.save_file: bool = self.get_config("save_file", False)
        self.save_voice: bool = self.get_config("save_voice", False)
        self.debug: bool = self.get_config("debug", False)
        self.self_nickname: str = self.get_config("self_nickname", "")
        self.permission_mode: str = self.get_config("permission_mode", "allow_list")
        self.group_allow_list: list[str] = self.get_config("group_allow_list", []) or []
        self.user_allow_list: list[str] = self.get_config("user_allow_list", []) or []
        self.group_deny_list: list[str] = self.get_config("group_deny_list", []) or []
        self.user_deny_list: list[str] = self.get_config("user_deny_list", []) or []
        self.group_at_me_only: bool = self.get_config("group_at_me_only", False)
        self.group_wake_words: list[str] = self.get_config("group_wake_words", []) or []

        # 朋友圈配置
        self.enable_moments: bool = self.get_config("enable_moments", False)
        self.moments_poll_interval: float = self.get_config("moments_poll_interval", 60.0)
        self.moments_fetch_count: int = self.get_config("moments_fetch_count", 10)
        self.moments_permission_mode: str = self.get_config("moments_permission_mode", "allow_list")
        self.moments_user_allow_list: list[str] = self.get_config("moments_user_allow_list", []) or []
        self.moments_user_deny_list: list[str] = self.get_config("moments_user_deny_list", []) or []

        self._client = WeChatClient(
            language=self.language,
            debug=self.debug,
            save_pic=self.save_pic,
            save_file=self.save_file,
            save_voice=self.save_voice,
            self_nickname=self.self_nickname,
        )
        self._shutdown_event = asyncio.Event()
        self._polling_task: Optional[asyncio.Task] = None
        self._seen_msg_ids: set[str] = set()
        self._seen_fingerprints: set[str] = set()

        # 朋友圈轮询状态
        self._moments_polling_task: Optional[asyncio.Task] = None
        self._known_feed_ids: deque[str] = deque(maxlen=500)

    async def start(self):
        """启动适配器，连接微信窗口并开始轮询"""
        try:
            await self._client.connect()
            self._running = True
            self._shutdown_event.clear()
            self._polling_task = asyncio.create_task(self._polling_loop())
            if self.enable_moments:
                self._moments_polling_task = asyncio.create_task(self._moments_polling_loop())
                logger.info("WeChat PC adapter started (with moments polling)")
            else:
                logger.info("WeChat PC adapter started (moments polling disabled)")
        except Exception as e:
            logger.error(f"Failed to start WeChat PC adapter: {e}")
            raise

    async def stop(self):
        """停止适配器，断开连接并清理资源"""
        self._running = False
        self._shutdown_event.set()
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        if self._moments_polling_task:
            self._moments_polling_task.cancel()
            try:
                await self._moments_polling_task
            except asyncio.CancelledError:
                pass
        await self._client.close()
        logger.info("WeChat PC adapter stopped")

    async def send_message(self, target_id: str, content: MessageContent, **kwargs) -> bool:
        """发送消息到指定会话

        Args:
            target_id: 目标会话名称（群名或好友名）
            content: 标准化消息内容
        """
        try:
            if content.text:
                await self._client.send_text(
                    target_id, content.text, at=content.at_targets or None
                )
            for img_path in content.images:
                if os.path.isfile(img_path):
                    await self._client.send_files(target_id, [img_path])
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {target_id}: {e}")
            return False

    async def parse_event(self, raw_event: dict) -> Optional[PlatformEvent]:
        """将原始微信消息转换为统一事件格式

        轮询模式下通常由内部直接 emit，但此方法提供标准解析入口。
        """
        msg = raw_event.get("_wechat_msg")
        session_name = raw_event.get("session_name", "")
        if not isinstance(msg, WeChatMessage):
            return None
        return self._build_event(session_name, msg)

    async def _polling_loop(self):
        """消息轮询主循环"""
        reconnect_attempts = 0
        max_reconnect_attempts = 5

        while not self._shutdown_event.is_set():
            try:
                new_messages = await self._client.poll_messages(max_round=5)
                reconnect_attempts = 0

                total = sum(len(v) for v in new_messages.values())
                if total > 0:
                    logger.debug(
                        f"[polling] Received {total} message(s) from "
                        f"{len(new_messages)} session(s)"
                    )

                for session_name, msgs in new_messages.items():
                    # 延迟识别未知会话的群聊属性
                    if session_name not in self._client._group_cache:
                        try:
                            await self._client.is_group_chat(session_name)
                        except Exception:
                            pass

                    new_count = 0
                    dup_count = 0

                    for msg in msgs:
                        # 去重检查
                        fp = (
                            f"{session_name}:{msg.sender_name}:"
                            f"{msg.sender_type}:{msg.msg_type}:{msg.content[:80]}"
                        )
                        if msg.msg_id and msg.msg_id in self._seen_msg_ids:
                            dup_count += 1
                            continue
                        if fp in self._seen_fingerprints:
                            dup_count += 1
                            continue

                        if msg.msg_id:
                            self._seen_msg_ids.add(msg.msg_id)
                            if len(self._seen_msg_ids) > 500:
                                self._seen_msg_ids = set(
                                    list(self._seen_msg_ids)[-300:]
                                )
                        self._seen_fingerprints.add(fp)
                        if len(self._seen_fingerprints) > 1000:
                            self._seen_fingerprints = set(
                                list(self._seen_fingerprints)[-600:]
                            )

                        # 跳过系统/时间/自己消息
                        if msg.msg_type == "sys" or msg.sender_type in (
                            "time",
                            "self",
                        ):
                            continue

                        is_group = self._client._group_cache.get(session_name, False)

                        # 启发式修正：私聊中 sender_name 与 session_name 相同
                        if (
                            is_group
                            and msg.sender_type == "friend"
                            and msg.sender_name == session_name
                        ):
                            is_group = False
                            self._client._group_cache[session_name] = False
                            self._client._save_group_cache()

                        # 权限检查
                        if not self._check_permission(session_name, is_group):
                            logger.debug(
                                f"[permission] Discarded from [{session_name}]"
                            )
                            continue

                        # 群聊 @/关键词唤醒检测
                        if is_group and self.group_at_me_only:
                            content_text = msg.content or ""
                            is_at_me = False
                            if self.self_nickname:
                                if (
                                    f"@{self.self_nickname}" in content_text
                                    or self.self_nickname in content_text
                                ):
                                    is_at_me = True
                            has_wake_word = any(
                                w in content_text for w in self.group_wake_words
                            )
                            if not (is_at_me or has_wake_word):
                                logger.debug(
                                    f"[convert] Group message discarded (no @): "
                                    f"[{session_name}] {content_text[:30]}"
                                )
                                continue

                        event = self._build_event(session_name, msg, is_group)
                        if event:
                            new_count += 1
                            await self.emit_event(event)

                    if new_count or dup_count:
                        logger.debug(
                            f"[polling] {session_name}: +{new_count} new, "
                            f"-{dup_count} dup"
                        )

            except WindowLostError:
                reconnect_attempts += 1
                if reconnect_attempts > max_reconnect_attempts:
                    logger.error(
                        "WeChat window lost too many times, stopping polling"
                    )
                    break
                logger.warning(
                    f"WeChat window lost, reconnecting... "
                    f"({reconnect_attempts}/{max_reconnect_attempts})"
                )
                try:
                    await asyncio.sleep(2.0)
                    await self._client.connect()
                except Exception as e:
                    logger.error(f"Reconnection failed: {e}")
            except Exception as e:
                logger.error(f"Polling error: {e}")

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=self.poll_interval
                )
            except asyncio.TimeoutError:
                pass

    @staticmethod
    def _name_matches(name: str, name_list: list[str]) -> bool:
        """精确昵称匹配（大小写不敏感）

        用于消息权限和朋友圈权限检查。
        注意：仅做精确匹配，子串不视为匹配以防止白名单绕过。
        """
        name_lower = name.strip().lower()
        for item in name_list:
            item_lower = item.lower()
            if name_lower == item_lower:
                return True
        return False

    def _check_permission(self, session_name: str, is_group: bool) -> bool:
        """白名单/黑名单权限检查"""
        session_clean = session_name.strip() if session_name else session_name

        if is_group:
            if self.permission_mode == "allow_list":
                return (
                    not self.group_allow_list
                    or self._name_matches(session_clean, self.group_allow_list)
                )
            elif self.permission_mode == "deny_list":
                return (
                    not self.group_deny_list
                    or not self._name_matches(session_clean, self.group_deny_list)
                )
            else:
                logger.warning(
                    "[WeChat] Unknown permission_mode '%s', default to deny",
                    self.permission_mode
                )
                return False
        else:
            if self.permission_mode == "allow_list":
                return (
                    not self.user_allow_list
                    or self._name_matches(session_clean, self.user_allow_list)
                )
            elif self.permission_mode == "deny_list":
                return (
                    not self.user_deny_list
                    or not self._name_matches(session_clean, self.user_deny_list)
                )
            else:
                logger.warning(
                    "[WeChat] Unknown permission_mode '%s', default to deny",
                    self.permission_mode
                )
                return False

    def _build_event(
        self, session_name: str, msg: WeChatMessage, is_group: bool = False
    ) -> Optional[PlatformEvent]:
        """将微信消息转换为统一 PlatformEvent"""
        images = []
        text = msg.content

        if msg.msg_type == "image":
            if os.path.isfile(msg.content):
                images.append(msg.content)
        elif msg.msg_type == "file":
            text = (
                f"[文件] {os.path.basename(msg.content)}"
                if os.path.isfile(msg.content)
                else msg.content
            )
        elif msg.msg_type == "voice":
            text = f"[语音] {msg.content}"

        content = MessageContent(text=text, images=images)
        event_type = EventType.GROUP_MESSAGE if is_group else EventType.PRIVATE_MESSAGE
        sender = SenderInfo(id=msg.sender_name, name=msg.sender_name)

        return PlatformEvent(
            platform=self.platform,
            event_type=event_type,
            sender=sender,
            content=content,
            raw_event={
                "session_name": session_name,
                "is_group": is_group,
                "sender_type": msg.sender_type,
                "msg_type": msg.msg_type,
                "raw_control": str(msg.raw_control) if msg.raw_control else None,
            },
            message_id=msg.msg_id or uuid.uuid4().hex,
            group_id=session_name if is_group else None,
            group_name=session_name if is_group else None,
        )

    # ---------- 朋友圈轮询 ----------

    async def _moments_polling_loop(self):
        """朋友圈内容轮询主循环

        包含重连机制（最多5次）、随机抖动（±20%）、空抓取告警（连续5次）。
        """
        logger.info("Moments polling started")
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        empty_fetch_count = 0
        max_empty_warnings = 5

        while not self._shutdown_event.is_set():
            try:
                feed_items = await self._client.get_moments_feed(count=self.moments_fetch_count)

                # 空抓取告警
                if not feed_items:
                    empty_fetch_count += 1
                    if empty_fetch_count >= max_empty_warnings:
                        logger.warning(
                            f"Moments polling: empty result for "
                            f"{empty_fetch_count} consecutive polls"
                        )
                else:
                    empty_fetch_count = 0
                    reconnect_attempts = 0  # 有数据视为连接正常
                    logger.info(
                        f"Moments polling: got {len(feed_items)} new post(s)"
                    )

                for item in feed_items:
                    item_id = item.get("id")
                    if not item_id or item_id in self._known_feed_ids:
                        continue
                    self._known_feed_ids.append(item_id)

                    text = item.get("text") or ""
                    if not text:
                        continue

                    user_name = item.get("user_name", "")
                    if not self._moments_check_permission(user_name):
                        logger.debug(
                            f"[moments] Permission denied: {user_name}"
                        )
                        continue

                    # 增强 raw_event：添加结构化调试信息
                    enriched_raw = dict(item)
                    enriched_raw["_parsed_at"] = datetime.now().isoformat()

                    event = PlatformEvent(
                        platform=PlatformType.WECHAT_MOMENTS,
                        event_type=EventType.MOMENTS_POST,
                        sender=SenderInfo(
                            id=item.get("user_id", ""),
                            name=user_name,
                        ),
                        content=MessageContent(text=text),
                        raw_event=enriched_raw,
                        message_id=item_id,
                    )
                    await self.emit_event(event)

                # 随机抖动（问题5）：±20%
                jitter = random.uniform(-0.2, 0.2)
                actual_interval = self.moments_poll_interval * (1.0 + jitter)
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=actual_interval
                )
            except asyncio.CancelledError:
                logger.info("Moments polling cancelled")
                break
            except asyncio.TimeoutError:
                continue
            except WindowLostError:
                reconnect_attempts += 1
                if reconnect_attempts > max_reconnect_attempts:
                    logger.error(
                        "Moments polling: window lost too many times, stopping"
                    )
                    break
                logger.warning(
                    f"Moments polling: window lost, reconnecting... "
                    f"({reconnect_attempts}/{max_reconnect_attempts})"
                )
                try:
                    await asyncio.sleep(2.0)
                    await self._client.connect()
                except Exception as e:
                    logger.error(f"Moments polling: reconnection failed: {e}")
            except Exception as e:
                logger.error(f"Moments polling error: {e}")
        logger.info("Moments polling stopped")

    def _moments_check_permission(self, user_name: str) -> bool:
        """朋友圈白名单/黑名单权限检查（按昵称）"""
        name = user_name.strip() if user_name else user_name

        if self.moments_permission_mode == "allow_list":
            return not self.moments_user_allow_list or self._name_matches(
                name, self.moments_user_allow_list
            )
        else:  # deny_list
            return not self.moments_user_deny_list or not self._name_matches(
                name, self.moments_user_deny_list
            )
