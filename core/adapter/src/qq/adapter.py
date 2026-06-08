import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

try:
    import websockets
except ImportError:
    websockets = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

from core.adapter.base import BaseAdapter
from core.adapter.event import (
    PlatformType,
    PlatformEvent,
    EventType,
    MessageContent,
    SenderInfo,
)
from ....utils import get_logger

logger = get_logger(__name__)


class QQAdapter(BaseAdapter):
    """QQ平台适配器

    基于 NapCat/OneBot 11 协议实现。
    需要配合 NapCatQQ 使用。

    Required:
        pip install websockets aiohttp

    Example Config:
        {
            "ws_url": "ws://localhost:3001",
            "http_url": "http://localhost:3000",
            "access_token": "",
            "auto_reconnect": true,
            "reconnect_interval": 5
        }
    """

    @property
    def platform(self) -> PlatformType:
        return PlatformType.QQ

    async def start(self):
        """启动QQ适配器，建立WebSocket连接"""
        if websockets is None:
            raise ImportError("websockets is required for QQ adapter. Install: pip install websockets")

        self.ws_url = self.get_config("ws_url", "ws://localhost:3001")
        self.http_url = self.get_config("http_url", "http://localhost:3000")
        self.access_token = self.get_config("access_token", "")
        self.auto_reconnect = self.get_config("auto_reconnect", True)
        self.reconnect_interval = self.get_config("reconnect_interval", 5)

        self._ws = None
        self._session = None
        self._reconnect_task = None
        self._receive_task = None

        self._running = True

        # 消息去重
        self._seen_msg_ids: set[str] = set()
        self._seen_fingerprints: set[str] = set()

        await self._connect()
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info(f"[QQ] Adapter started, connecting to {self.ws_url}")

    async def stop(self):
        """停止QQ适配器"""
        self._running = False

        # 取消并等待重连任务
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        self._reconnect_task = None

        # 取消并等待接收循环任务
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        self._receive_task = None

        if self._ws:
            await self._ws.close()

        if self._session and aiohttp:
            await self._session.close()

    async def _connect(self):
        """建立WebSocket连接"""
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        try:
            self._ws = await websockets.connect(self.ws_url, additional_headers=headers)
            logger.info(f"[QQ] Connected to {self.ws_url}")
        except Exception as e:
            logger.error(f"[QQ] Connection failed: {e}")
            self._ws = None
            raise

    def _schedule_reconnect(self):
        """调度重连"""
        if not self._running:
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """重连循环：等待间隔 → 重新连接 → 重启接收循环"""
        await asyncio.sleep(self.reconnect_interval)
        try:
            await self._connect()
            logger.info(f"[QQ] Reconnected, restarting receive loop")
            await self._receive_loop()
        except Exception as e:
            logger.error(f"[QQ] Reconnect failed: {e}")
            if self.auto_reconnect and self._running:
                self._schedule_reconnect()

    async def _receive_loop(self):
        """消息接收循环"""
        try:
            while self._running:
                try:
                    if not self._ws:
                        await asyncio.sleep(1)
                        continue

                    message = await self._ws.recv()
                    data = json.loads(message)

                    if "status" in data:
                        self._handle_api_response(data)
                    elif "post_type" in data:
                        event = self.parse_event(data)
                        if event:
                            msg_id = event.message_id
                            if msg_id and msg_id in self._seen_msg_ids:
                                logger.debug(f"[QQ] Duplicate message (id={msg_id}), skipped")
                                continue

                            fp = (
                                f"{event.message_id}:{event.sender.id}:"
                                f"{event.content.text or ''}"
                            )
                            if msg_id:
                                self._seen_msg_ids.add(msg_id)
                                if len(self._seen_msg_ids) > 1000:
                                    self._seen_msg_ids = set(list(self._seen_msg_ids)[-500:])

                            if fp in self._seen_fingerprints:
                                logger.debug(f"[QQ] Duplicate message (fingerprint matched), skipped")
                                continue

                            self._seen_fingerprints.add(fp)
                            if len(self._seen_fingerprints) > 1000:
                                self._seen_fingerprints = set(list(self._seen_fingerprints)[-500:])

                            await self.emit_event(event)

                except websockets.exceptions.ConnectionClosed:
                    logger.info("[QQ] Connection closed")
                    if self.auto_reconnect and self._running:
                        self._schedule_reconnect()
                    break
                except asyncio.CancelledError:
                    logger.info("[QQ] Receive loop cancelled")
                    break
                except Exception as e:
                    logger.info(f"[QQ] Error in receive loop: {e}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("[QQ] Receive loop cancelled (outer)")
        finally:
            logger.info("[QQ] Receive loop ended")

    def parse_event(self, raw_event: Dict[str, Any]) -> Optional[PlatformEvent]:
        """解析OneBot事件为统一格式"""
        post_type = raw_event.get("post_type")

        if post_type != "message":
            return None

        message_type = raw_event.get("message_type")
        user_id = str(raw_event.get("user_id", ""))
        group_id = raw_event.get("group_id")
        message_id = str(raw_event.get("message_id", ""))

        # 解析消息内容
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

    def _handle_api_response(self, data: Dict[str, Any]) -> None:
        """处理 OneBot API 响应，缓存已发送消息的 ID"""
        if data.get("status") == "ok":
            message_id = data.get("data", {}).get("message_id")
            if message_id:
                from ...sent_message_cache import sent_message_cache
                sent_message_cache.add(str(message_id))

    def _parse_message_content(self, message: Any) -> MessageContent:
        """解析OneBot消息段"""
        text_parts = []
        images = []
        at_targets = []
        reply_to = None

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

        return MessageContent(
            text=" ".join(text_parts) if text_parts else None,
            images=images,
            at_targets=at_targets,
            reply_to=reply_to,
        )

    async def send_message(self, target_id: str, content: MessageContent, **kwargs) -> bool:
        """发送消息（使用 WebSocket）"""
        try:
            # 构建消息
            message_segments = []

            if content.text:
                message_segments.append({
                    "type": "text",
                    "data": {"text": content.text}
                })

            for img_url in content.images:
                message_segments.append({
                    "type": "image",
                    "data": {"file": img_url}
                })

            # 从 kwargs 获取 is_group 参数
            is_group = kwargs.get('is_group', False)
            
            # 构建 OneBot API 请求
            if is_group:  # 群消息
                api_action = "send_group_msg"
                params = {
                    "group_id": int(target_id),
                    "message": message_segments
                }
            else:  # 私聊消息
                api_action = "send_private_msg"
                params = {
                    "user_id": int(target_id),
                    "message": message_segments
                }

            # 通过 WebSocket 发送 API 请求
            if not self._ws:
                logger.info("[QQ] WebSocket not connected")
                return False

            request = {
                "action": api_action,
                "params": params,
                "echo": str(asyncio.get_event_loop().time())  # 用于匹配响应
            }

            await self._ws.send(json.dumps(request))
            logger.info(f"[QQ] Message sent via WebSocket: {api_action}")
            return True

        except Exception as e:
            logger.info(f"[QQ] Failed to send message: {e}")
            return False
