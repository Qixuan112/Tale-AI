import asyncio
import json
from collections import OrderedDict
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.adapter.base import BaseAdapter
from core.adapter.event import (
    PlatformType,
    PlatformEvent,
    EventType,
    MessageContent,
    SenderInfo,
)
from ....utils import get_logger
from .napcat_client import NapCatWebSocketClient

logger = get_logger(__name__)

# 去重窗口大小（LRU 淘汰）
_DEDUP_MAX = 1000
_DEDUP_TRIM = 500


class QQAdapter(BaseAdapter):
    """QQ平台适配器

    基于 NapCat/OneBot 11 协议实现。
    需要配合 NapCatQQ 使用。

    Required:
        pip install websockets

    Example Config:
        {
            "ws_url": "ws://localhost:3001",
            "http_url": "http://localhost:3000",
            "access_token": "",
            "bot_uin": "123456789",
            "auto_reconnect": true
        }
    """

    @property
    def platform(self) -> PlatformType:
        return PlatformType.QQ

    async def start(self):
        """启动QQ适配器，建立WebSocket连接"""
        self.ws_url = self.get_config("ws_url", "ws://localhost:3001")
        self.http_url = self.get_config("http_url", "http://localhost:3000")
        self.access_token = self.get_config("access_token", "")
        self.bot_uin = self.get_config("bot_uin") or self.get_config("bot_pid", "")
        self.auto_reconnect = self.get_config("auto_reconnect", True)

        # 消息去重（OrderedDict 实现 FIFO/LRU 语义）
        self._seen_msg_ids: OrderedDict[str, None] = OrderedDict()
        self._seen_fingerprints: OrderedDict[str, None] = OrderedDict()

        # 创建 NapCatWebSocketClient
        self.client = NapCatWebSocketClient()
        self.client.set_message_callback(self._on_raw_message)

        # 预先创建 _run_done Future：run() 内部会 await connect() 等异步操作，
        # 若不预创建，start() 在 create_task 后立即读 self.client._run_done 时
        # run() 协程可能尚未执行到创建 future 那行，_run_done 仍为 None，
        # 导致 asyncio.wait_for(None) 抛 TypeError，适配器启动失败。
        loop = asyncio.get_running_loop()
        self.client._run_done = loop.create_future()

        # 在后台运行 client（通过 _run_done 观察结果）
        self._client_task = asyncio.create_task(
            self.client.run(
                bot_uin=self.bot_uin,
                ws_url=self.ws_url,
                access_token=self.access_token,
            )
        )

        # 等待 client.run 完成（成功或失败），最多 20 秒
        self._running = True
        try:
            ok = await asyncio.wait_for(self.client._run_done, timeout=20)
            if ok:
                logger.info(f"[QQ] Adapter started, connected to {self.ws_url}")
            else:
                logger.warning(f"[QQ] Adapter startup failed (login check)")
        except asyncio.TimeoutError:
            logger.warning(
                f"[QQ] Adapter start timeout (ws connected but login pending)"
            )

    async def stop(self):
        """停止QQ适配器"""
        self._running = False
        await self.client.close()
        if self._client_task and not self._client_task.done():
            self._client_task.cancel()
            try:
                await self._client_task
            except asyncio.CancelledError:
                pass
        self._client_task = None
        logger.info("[QQ] Adapter stopped")

    # ── 消息回调 ──────────────────────────────────────────────────────

    async def _on_raw_message(self, data: dict):
        """收到原始消息回调（由 NapCatWebSocketClient 的消息循环调用）。

        API 响应（含 echo）已由 Client 层消费并路由到对应的 Future，
        此处只处理 ``post_type`` 事件。
        """
        if "post_type" not in data:
            return

        # 处理元事件 —— 仅日志
        post_type = data.get("post_type")
        if post_type == "meta_event":
            return

        # 只关注消息事件
        if post_type == "notice":
            await self._on_notice_event(data)
            return
        elif post_type != "message":
            return

        event = await self.parse_event(data)
        if not event:
            return

        # 去重（message_id 维度）
        msg_id = event.message_id
        if msg_id and msg_id in self._seen_msg_ids:
            logger.debug(f"[QQ] Duplicate message (id={msg_id}), skipped")
            return

        # fingerprint 去重（不含 message_id，用于捕获内容相同的重发）
        fp = (
            f"{event.sender.id}:{event.content.text or ''}"
        )
        if fp in self._seen_fingerprints:
            logger.debug("[QQ] Duplicate message (fingerprint matched), skipped")
            return

        if msg_id:
            self._seen_msg_ids[msg_id] = None
            if len(self._seen_msg_ids) > _DEDUP_MAX:
                self._seen_msg_ids = OrderedDict(
                    list(self._seen_msg_ids.items())[-_DEDUP_TRIM:]
                )
        self._seen_fingerprints[fp] = None
        if len(self._seen_fingerprints) > _DEDUP_MAX:
            self._seen_fingerprints = OrderedDict(
                list(self._seen_fingerprints.items())[-_DEDUP_TRIM:]
            )

        # 获取引用消息原文
        if event.content.reply_to:
            try:
                msg_data = await asyncio.wait_for(
                    self.get_msg(event.content.reply_to), timeout=2.0
                )
                if msg_data and isinstance(msg_data, dict):
                    raw_msg = msg_data.get("message")
                    sender = msg_data.get("sender", {})
                    sender_name = sender.get("nickname") or sender.get("user_id") or "?"
                    original_text = self._parse_message_content(raw_msg).text or ""
                    if original_text.strip():
                        event.content.reply_text = f"{sender_name}: {original_text}"
                        logger.debug("[QQ] 已追溯引用原文: %s", event.content.reply_text)
            except Exception as e:
                logger.warning("[QQ] 获取引用原文失败: %s", e)

        # 异步触发事件（不阻塞消息接收）
        task = asyncio.create_task(self.emit_event(event))
        task.add_done_callback(
            lambda t: logger.error(
                "[QQ] emit_event 异常: %s", t.exception()
            ) if t.exception() else None
        )

    # ── 事件解析 ──────────────────────────────────────────────────────

    async def parse_event(self, raw_event: Dict[str, Any]) -> Optional[PlatformEvent]:
        """解析OneBot事件为统一格式"""
        post_type = raw_event.get("post_type")

        if post_type != "message":
            return None

        message_type = raw_event.get("message_type")
        user_id = str(raw_event.get("user_id", ""))
        group_id = raw_event.get("group_id")
        message_id = str(raw_event.get("message_id", ""))

        # 解析消息内容（纯 CPU 解析，保持 sync）
        content = self._parse_message_content(raw_event.get("message", []))

        # 确定事件类型
        if message_type == "group":
            event_type = EventType.GROUP_MESSAGE
        elif message_type == "private":
            event_type = EventType.PRIVATE_MESSAGE
        else:
            event_type = EventType.MESSAGE

        # 构建发送者信息
        sender_info = raw_event.get("sender", {})
        sender = SenderInfo(
            id=user_id,
            name=sender_info.get("nickname", user_id),
            avatar=None,
            is_bot=False,
        )

        return PlatformEvent(
            platform=PlatformType.QQ,
            event_type=event_type,
            sender=sender,
            content=content,
            raw_event=raw_event,
            timestamp=datetime.now(),
            message_id=message_id,
            group_id=str(group_id) if group_id else None,
        )

    # ── 消息内容解析 ──────────────────────────────────────────────────

    @staticmethod
    def _extract_card_info(card_json: str) -> Dict[str, Any]:
        """解析 OneBot json 段中的卡片信息为结构化 dict

        参考 KiraAI.extract_card_info 实现
        """
        try:
            data = json.loads(card_json)
        except (json.JSONDecodeError, TypeError):
            return {"raw": card_json} if isinstance(card_json, str) else {}

        result = {}
        for key in ("app", "prompt", "bizsrc", "view"):
            if key in data:
                result[key] = data[key]

        meta = data.get("meta", {})
        content = (
            meta.get("detail_1")
            or meta.get("news")
            or meta.get("music")
            or meta
        )
        if isinstance(content, dict):
            for key in ("title", "desc", "jumpUrl", "qqdocurl", "tag"):
                if key in content:
                    result[key] = content[key]
        return result

    def _parse_message_content(self, message: Any) -> MessageContent:
        """解析OneBot消息段"""
        text_parts = []
        images = []
        at_targets = []
        reply_to = None
        faces = []
        stickers = []
        videos = []
        voices = []
        json_cards = []

        if isinstance(message, str):
            # CQ码格式
            text_parts.append(message)
        elif isinstance(message, list):
            # 消息段数组格式
            for segment in message:
                seg_type = segment.get("type")
                data = segment.get("data", {})

                if seg_type == "text":
                    text_parts.append(data.get("text", ""))
                elif seg_type == "image":
                    images.append(data.get("url", data.get("file", "")))
                elif seg_type == "at":
                    at_targets.append(data.get("qq", ""))
                elif seg_type == "reply":
                    reply_to = str(data.get("id", ""))
                elif seg_type == "face":
                    faces.append(dict(data))
                elif seg_type == "mface":
                    stickers.append(dict(data))
                elif seg_type == "video":
                    videos.append(dict(data))
                elif seg_type == "record":
                    voices.append({
                        "url": data.get("url", ""),
                        "file": data.get("file", ""),
                        "path": data.get("path", ""),
                    })
                elif seg_type == "json":
                    card_info = self._extract_card_info(data.get("data", ""))
                    json_cards.append(card_info)

        return MessageContent(
            text=" ".join(text_parts) if text_parts else None,
            images=images,
            at_targets=at_targets,
            reply_to=reply_to,
            faces=faces,
            stickers=stickers,
            videos=videos,
            voices=voices,
            json_cards=json_cards,
        )

    # ── 消息发送 ──────────────────────────────────────────────────────

    async def send_message(
        self, target_id: str, content: MessageContent, **kwargs
    ) -> bool:
        """发送消息（通过 NapCatWebSocketClient）"""
        try:
            # 构建消息
            message_segments = []

            # 引用回复（必须先于其他段，OneBot 协议要求）
            if content.reply_to:
                message_segments.append(
                    {"type": "reply", "data": {"id": content.reply_to}}
                )

            # 群聊回复时，需要 @ 发送者才能触发实际提醒
            if kwargs.get("is_group") and content.at_targets:
                for at_qq in content.at_targets:
                    message_segments.append(
                        {"type": "at", "data": {"qq": at_qq}}
                    )

            if content.text:
                message_segments.append(
                    {"type": "text", "data": {"text": content.text}}
                )

            for img_url in content.images:
                message_segments.append(
                    {"type": "image", "data": {"file": img_url}}
                )

            # 从 kwargs 获取 is_group 参数
            is_group = kwargs.get("is_group", False)

            # 构建 OneBot API 请求
            if is_group:
                api_action = "send_group_msg"
                params = {"group_id": int(target_id), "message": message_segments}
            else:
                api_action = "send_private_msg"
                params = {"user_id": int(target_id), "message": message_segments}

            if not self.client.websocket:
                logger.warning("[QQ] send_message 失败: WebSocket 未连接 (target=%s)", target_id)
                return False

            result = await self.client.send_action(api_action, params)
            if result is None:
                logger.warning(
                    "[QQ] send_message 失败: 未收到响应 (target=%s, action=%s)",
                    target_id, api_action,
                )
                return False
            if result.get("status") != "ok":
                logger.warning(
                    "[QQ] send_message 失败: status=%s, retcode=%s (target=%s)",
                    result.get("status"), result.get("retcode", "unknown"), target_id,
                )
                return False

            # 缓存已发送消息 ID（用于引用唤醒）
            message_id = (result.get("data") or {}).get("message_id")
            if message_id:
                from ...sent_message_cache import sent_message_cache

                sent_message_cache.add(str(message_id))

            return True

        except Exception as e:
            logger.info(f"[QQ] Failed to send message: {e}")
            return False

    # ── 追溯原文 ─────────────────────────────────────────────────────

    async def get_msg(self, message_id: str) -> Optional[dict]:
        """调用 OneBot get_msg API 获取消息原文

        Args:
            message_id: 消息 ID

        Returns:
            消息数据 dict（含 sender、message 等字段），失败返回 None
        """
        return await self.api_call("get_msg", {"message_id": int(message_id)})

    # ── 通知事件 ─────────────────────────────────────────────────────

    async def _on_notice_event(self, data: dict):
        """处理 notice 事件（戳一戳、入群、禁言等）"""
        notice_type = data.get("notice_type", "")
        sub_type = data.get("sub_type", "")
        user_id = str(data.get("user_id", ""))
        target_id = str(data.get("target_id", ""))
        group_id = data.get("group_id")
        sender = SenderInfo(id=user_id, name=user_id, is_bot=False)

        if notice_type == "notify" and sub_type == "poke":
            content = MessageContent(text=f"[戳一戳] 用户 {user_id} 戳了 {target_id}")
        else:
            content = MessageContent(text=f"[通知] {notice_type}/{sub_type}")

        event = PlatformEvent(
            platform=PlatformType.QQ,
            event_type=EventType.NOTICE,
            sender=sender,
            content=content,
            raw_event=data,
            timestamp=datetime.now(),
            message_id=None,
            group_id=str(group_id) if group_id else None,
        )

        task = asyncio.create_task(self.emit_event(event))
        task.add_done_callback(
            lambda t: logger.error(
                "[QQ] emit_event(notice) 异常: %s", t.exception()
            ) if t.exception() else None
        )

    # ── API 调用 ─────────────────────────────────────────────────────

    async def _call_action(self, action: str, params: dict = None) -> Optional[dict]:
        """发送 OneBot API 请求，返回完整响应（含 status/retcode/data）。"""
        if not self.client.websocket:
            logger.warning("[QQ] WebSocket not connected for API call")
            return None
        return await self.client.send_action(action, params)

    async def api_call(self, action: str, params: dict = None) -> Optional[dict]:
        """发送 OneBot API 请求，仅返回 data 部分。

        Args:
            action: OneBot API 动作名，如 get_group_member_list
            params: 参数字典

        Returns:
            API 响应的 data 部分，失败返回 None
        """
        result = await self._call_action(action, params)
        if result is None:
            return None
        return result.get("data")

    async def get_msg(self, message_id: str) -> Optional[dict]:
        """获取消息原文。

        若 message_id 不合法（非纯数字），直接返回 None 避免 int() 异常。
        """
        if not message_id or not message_id.isdigit():
            logger.warning("[QQ] get_msg 跳过非法 message_id: %s", message_id)
            return None
        return await self.api_call("get_msg", {"message_id": int(message_id)})


class QQApiClient:
    """QQ OneBot API 客户端，供工具函数使用"""

    _adapter: Optional[QQAdapter] = None

    @classmethod
    def bind(cls, adapter: QQAdapter):
        cls._adapter = adapter

    @classmethod
    async def get_group_member_list(cls, group_id: str) -> List[dict]:
        """获取群成员列表

        Returns:
            [{"user_id": "123", "nickname": "浪子"}, ...]
        """
        if not cls._adapter:
            logger.warning("[QQApi] QQAdapter not bound")
            return []
        data = await cls._adapter.api_call(
            "get_group_member_list", {"group_id": int(group_id)}
        )
        if not data:
            return []
        members = data if isinstance(data, list) else data.get("list", data)
        return [
            {
                "user_id": str(m.get("user_id", "")),
                "nickname": m.get("nickname", "")
                or m.get("card", ""),
            }
            for m in members
        ]

    @classmethod
    async def delete_msg(cls, message_id: str) -> bool:
        """撤回消息

        Args:
            message_id: 要撤回的消息 ID

        Returns:
            是否成功
        """
        if not message_id or not message_id.isdigit():
            logger.warning("[QQApi] delete_msg 跳过非法 message_id: %s", message_id)
            return False
        try:
            result = await cls._adapter._call_action(
                "delete_msg", {"message_id": int(message_id)}
            )
            return result is not None and result.get("status") == "ok"
        except Exception as e:
            logger.warning("[QQApi] delete_msg 失败: %s", e)
            return False
