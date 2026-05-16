from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Optional, Union

from core.logging_manager import get_logger
from core.adapter.adapter_utils import IMAdapter
from core.chat import KiraMessageEvent, KiraIMMessage, MessageChain, KiraIMSentResult
from core.chat import Session, Group, User
from core.chat.message_elements import (
    Text,
    Image,
    At,
    Reply,
    Emoji,
    Sticker,
    Record,
    File,
    Video
)

from .wechat_client import WeChatClient, WeChatClientError, WindowLostError, WeChatMessage

logger = get_logger("wechat_pc", "green")


class WeChatPCAdapter(IMAdapter):
    def __init__(self, info, loop: asyncio.AbstractEventLoop, event_bus: asyncio.Queue, llm_api):
        super().__init__(info, loop, event_bus, llm_api)

        self.poll_interval: float = self.config.get("poll_interval", 2.0)
        self.language: str = self.config.get("language", "cn")
        self.save_pic: bool = self.config.get("save_pic", False)
        self.save_file: bool = self.config.get("save_file", False)
        self.save_voice: bool = self.config.get("save_voice", False)
        self.debug: bool = self.config.get("debug", False)
        self.self_nickname: str = self.config.get("self_nickname", "")
        self.group_at_me_only: bool = self.config.get("group_at_me_only", False)
        self.group_wake_words: list[str] = self.config.get("group_wake_words", []) or []

        self.message_types = ["text", "img", "at", "record", "file"]

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
        self._seen_fingerprints: set[str] = set()  # 基于内容指纹的去重兜底（应对 RuntimeId 变化）

    async def start(self):
        try:
            await self._client.connect()
            self._shutdown_event.clear()
            self._polling_task = asyncio.create_task(self._polling_loop())
            logger.info("WeChat PC adapter started")
        except Exception as e:
            logger.error(f"Failed to start WeChat PC adapter: {e}")
            raise

    async def stop(self):
        self._shutdown_event.set()
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        await self._client.close()
        logger.info("WeChat PC adapter stopped")

    def get_client(self):
        return self._client

    async def _polling_loop(self):
        reconnect_attempts = 0
        max_reconnect_attempts = 5

        while not self._shutdown_event.is_set():
            try:
                new_messages = await self._client.poll_messages(max_round=5)
                reconnect_attempts = 0

                total_msgs = sum(len(v) for v in new_messages.values())
                if total_msgs > 0:
                    logger.debug(f"[polling] Received {total_msgs} message(s) from {len(new_messages)} session(s)")

                # 延迟识别未知会话的群聊属性
                unknown_sessions = [
                    s for s in new_messages.keys()
                    if s not in self._client._group_cache
                ]
                for session_name in unknown_sessions:
                    try:
                        await self._client.is_group_chat(session_name)
                    except Exception:
                        pass

                for session_name, msgs in new_messages.items():
                    new_count = 0
                    dup_count = 0
                    for msg in msgs:
                        # 消息去重：先用 RuntimeId，再用内容指纹兜底
                        fp = f"{session_name}:{msg.sender_name}:{msg.sender_type}:{msg.msg_type}:{msg.content[:80]}"
                        if msg.msg_id and msg.msg_id in self._seen_msg_ids:
                            dup_count += 1
                            continue
                        if fp in self._seen_fingerprints:
                            dup_count += 1
                            continue
                        if msg.msg_id:
                            self._seen_msg_ids.add(msg.msg_id)
                            if len(self._seen_msg_ids) > 500:
                                self._seen_msg_ids = set(list(self._seen_msg_ids)[-300:])
                        self._seen_fingerprints.add(fp)
                        if len(self._seen_fingerprints) > 1000:
                            self._seen_fingerprints = set(list(self._seen_fingerprints)[-600:])

                        event = self._convert_to_kira_event(session_name, msg)
                        if event:
                            new_count += 1
                            self.publish(event)

                    if new_count or dup_count:
                        logger.debug(
                            f"[polling] {session_name}: +{new_count} new, -{dup_count} dup"
                        )

            except WindowLostError:
                reconnect_attempts += 1
                if reconnect_attempts > max_reconnect_attempts:
                    logger.error("WeChat window lost too many times, stopping polling")
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
    def _is_valid_media_source(content: str) -> bool:
        if not content:
            return False
        if content.startswith(("http://", "https://", "data:", "file:///", "base64://")):
            return True
        if os.path.isfile(content):
            return True
        return False

    def _convert_to_kira_event(
        self, session_name: str, msg: WeChatMessage
    ) -> Optional[KiraMessageEvent]:
        # 跳过系统消息和时间消息
        if msg.msg_type == "sys" or msg.sender_type == "time":
            logger.debug(f"[convert] Skipped sys/time message from [{session_name}]")
            return None

        # 跳过自己发送的消息，避免自循环
        if msg.sender_type == "self":
            logger.debug(f"[convert] Skipped self message from [{session_name}]: {msg.content[:50] if msg.content else ''}")
            return None

        is_group = self._client._group_cache.get(session_name)
        if is_group is None:
            is_group = False

        # 修正：私聊中 sender_name 与 session_name 相同；群聊中 sender 是成员名，session 是群名
        if is_group and msg.sender_type == "friend" and msg.sender_name == session_name:
            is_group = False
            self._client._group_cache[session_name] = False
            self._client._save_group_cache()
            logger.debug(f"[convert] Heuristic fix: '{session_name}' corrected from group to private chat")

        session_name_clean = session_name.strip() if session_name else session_name

        def _name_match(name: str, name_list: list[str]) -> bool:
            """支持精确匹配、子串匹配、大小写不敏感匹配"""
            name_lower = name.lower()
            for item in name_list:
                item_lower = item.lower()
                if name == item or name_lower == item_lower:
                    return True
                if item_lower in name_lower or name_lower in item_lower:
                    return True
            return False

        # 权限检查：白名单/黑名单为空时默认允许所有
        if is_group:
            should_process = False
            if self.permission_mode == "allow_list":
                if not self.group_list or _name_match(session_name_clean, self.group_list):
                    should_process = True
            elif self.permission_mode == "deny_list":
                if not self.group_list or not _name_match(session_name_clean, self.group_list):
                    should_process = True
            logger.debug(
                f"[permission] group mode={self.permission_mode}, "
                f"list={self.group_list}, session={session_name!r} "
                f"(clean={session_name_clean!r}), is_group={is_group}, "
                f"should_process={should_process}"
            )
            if not should_process:
                return None
        else:
            should_process = False
            if self.permission_mode == "allow_list":
                if not self.user_list or _name_match(session_name_clean, self.user_list):
                    should_process = True
            elif self.permission_mode == "deny_list":
                if not self.user_list or not _name_match(session_name_clean, self.user_list):
                    should_process = True
            logger.debug(
                f"[permission] user mode={self.permission_mode}, "
                f"list={self.user_list}, session={session_name!r} "
                f"(clean={session_name_clean!r}), is_group={is_group}, "
                f"should_process={should_process}"
            )
            if not should_process:
                return None

        # 构造 MessageChain
        elements = []
        if msg.msg_type == "text":
            elements.append(Text(msg.content))
        elif msg.msg_type == "image":
            if self._is_valid_media_source(msg.content):
                elements.append(Image(msg.content))
            else:
                elements.append(Text(msg.content))
        elif msg.msg_type == "file":
            if self._is_valid_media_source(msg.content):
                file_name = os.path.basename(msg.content) if os.path.isfile(msg.content) else None
                elements.append(File(msg.content, name=file_name))
            else:
                elements.append(Text(msg.content))
        elif msg.msg_type == "voice":
            if self._is_valid_media_source(msg.content):
                elements.append(Record(msg.content))
            else:
                elements.append(Text(msg.content))
        else:
            elements.append(Text(msg.content))

        chain = MessageChain(elements or [Text("[Empty]")])
        timestamp = int(time.time())

        # 群聊 @/关键词唤醒检测
        is_mentioned = True
        if is_group and self.group_at_me_only:
            content_text = msg.content or ""
            is_at_me = False
            if self.self_nickname:
                # 检测文本中是否 @ 了自己（支持 "@昵称" 或昵称直接出现）
                if f"@{self.self_nickname}" in content_text or self.self_nickname in content_text:
                    is_at_me = True
            has_wake_word = any(w in content_text for w in self.group_wake_words)
            is_mentioned = is_at_me or has_wake_word

            if not is_mentioned:
                logger.debug(
                    f"[convert] Group message discarded (no @ or wake word): "
                    f"[{session_name}] {content_text[:30]}"
                )

        if is_group:
            group_obj = Group(group_id=session_name, group_name=session_name)
            sender_obj = User(user_id=msg.sender_name, nickname=msg.sender_name)
            message_obj = KiraIMMessage(
                timestamp=timestamp,
                group=group_obj,
                sender=sender_obj,
                is_mentioned=is_mentioned,
                message_id=msg.msg_id or uuid.uuid4().hex,
                self_id=self.self_nickname or "",
                chain=chain,
                raw_message={"wxauto_raw": str(msg.raw_control) if msg.raw_control else None},
            )
        else:
            sender_obj = User(user_id=session_name, nickname=session_name)
            message_obj = KiraIMMessage(
                timestamp=timestamp,
                sender=sender_obj,
                is_mentioned=True,
                message_id=msg.msg_id or uuid.uuid4().hex,
                self_id=self.self_nickname or "",
                chain=chain,
                raw_message={"wxauto_raw": str(msg.raw_control) if msg.raw_control else None},
            )

        event = KiraMessageEvent(
            adapter=self.info,
            message_types=self.message_types,
            message=message_obj,
            timestamp=timestamp,
        )
        if is_mentioned:
            event.trigger(force=True)
            logger.info(f"[convert] Event triggered for [{session_name}] content=[{msg.content[:30] if msg.content else ''}]")
        else:
            event.discard()
        return event

    async def send_group_message(
        self, group_id: Union[int, str], send_message_obj: MessageChain
    ) -> Optional[KiraIMSentResult]:
        return await self._send_to_session(str(group_id), send_message_obj)

    async def send_direct_message(
        self, user_id: Union[int, str], send_message_obj: MessageChain
    ) -> Optional[KiraIMSentResult]:
        return await self._send_to_session(str(user_id), send_message_obj)

    async def _send_to_session(self, who: str, chain: MessageChain) -> KiraIMSentResult:
        try:
            idx = 0
            while idx < len(chain):
                ele = chain[idx]

                if isinstance(ele, Text):
                    text_parts = []
                    at_list = []
                    while idx < len(chain) and isinstance(chain[idx], (Text, At)):
                        part = chain[idx]
                        if isinstance(part, Text):
                            text_parts.append(part.text)
                        elif isinstance(part, At):
                            if part.pid == "all":
                                text_parts.append("@所有人")
                            elif part.nickname:
                                text_parts.append(f"@{part.nickname}")
                                at_list.append(part.nickname)
                            else:
                                text_parts.append(f"@{part.pid}")
                                at_list.append(part.pid)
                        idx += 1

                    text = "".join(text_parts)
                    if text:
                        await self._client.send_text(who, text, at=at_list if at_list else None)
                    continue

                elif isinstance(ele, Image):
                    img_path = await ele.to_path()
                    await self._client.send_files(who, [img_path])

                elif isinstance(ele, File):
                    file_path = await ele.to_path()
                    await self._client.send_files(who, [file_path])

                elif isinstance(ele, Video):
                    video_path = await ele.to_path()
                    await self._client.send_files(who, [video_path])

                elif isinstance(ele, Record):
                    record_path = await ele.to_path()
                    await self._client.send_files(who, [record_path])

                else:
                    text = getattr(ele, "text", str(ele))
                    await self._client.send_text(who, text)

                idx += 1

            return KiraIMSentResult(message_id=uuid.uuid4().hex, ok=True)
        except Exception as e:
            logger.error(f"Failed to send message to {who}: {e}")
            return KiraIMSentResult(ok=False, err=str(e))
