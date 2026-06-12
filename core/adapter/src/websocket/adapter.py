import asyncio
import json
from typing import Dict, Any, Optional, Set
from datetime import datetime

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None
    WebSocketServerProtocol = None
    WebSocketClientProtocol = None

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


class WebSocketAdapter(BaseAdapter):
    """通用 WebSocket 适配器

    支持两种运行模式:
    1. Server 模式: 作为 WebSocket 服务端，等待客户端连接
    2. Client 模式: 作为 WebSocket 客户端，主动连接服务端

    Example Config:
        Server 模式:
        {
            "mode": "server",
            "host": "0.0.0.0",
            "port": 8080,
            "path": "/ws"
        }

        Client 模式:
        {
            "mode": "client",
            "url": "ws://localhost:8080/ws",
            "auto_reconnect": true,
            "reconnect_interval": 5
        }
    """

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WEBSOCKET

    async def start(self):
        """启动 WebSocket 适配器"""
        if websockets is None:
            raise ImportError("websockets is required. Install: pip install websockets")

        self.mode = self.get_config("mode", "server")
        self._running = True

        if self.mode == "server":
            await self._start_server()
        else:
            await self._start_client()

    async def _start_server(self):
        """启动 WebSocket 服务端"""
        self.host = self.get_config("host", "0.0.0.0")
        self.port = self.get_config("port", 8080)
        self.path = self.get_config("path", "/ws")

        self._clients: Dict[str, WebSocketServerProtocol] = {}
        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            subprotocols=["tale-protocol"]
        )

        logger.info(f"[WebSocket] Server started at ws://{self.host}:{self.port}{self.path}")

    async def _start_client(self):
        """启动 WebSocket 客户端"""
        self.url = self.get_config("url", "ws://localhost:8080/ws")
        self.auto_reconnect = self.get_config("auto_reconnect", True)
        self.reconnect_interval = self.get_config("reconnect_interval", 5)

        self._ws: Optional[WebSocketClientProtocol] = None
        self._reconnect_task = None
        self._receive_task = None

        await self._connect()

        # 启动消息接收循环（保存引用以便正确清理）
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _connect(self):
        """建立客户端连接"""
        try:
            self._ws = await websockets.connect(self.url)
            logger.info(f"[WebSocket] Connected to {self.url}")
        except Exception as e:
            logger.info(f"[WebSocket] Connection failed: {e}")
            if self.auto_reconnect:
                self._schedule_reconnect()

    def _schedule_reconnect(self):
        """调度重连"""
        if not self._running:
            return

        async def reconnect():
            await asyncio.sleep(self.reconnect_interval)
            if self._running:
                await self._connect()

        self._reconnect_task = asyncio.create_task(reconnect())

    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """处理服务端客户端连接"""
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self._clients[client_id] = websocket
        logger.info(f"[WebSocket] Client connected: {client_id}")

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    event = self._parse_client_message(data, client_id)
                    if event:
                        await self.emit_event(event)
                except json.JSONDecodeError:
                    logger.info(f"[WebSocket] Invalid JSON from {client_id}: {message}")
                except Exception as e:
                    logger.info(f"[WebSocket] Error handling message from {client_id}: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"[WebSocket] Client disconnected: {client_id}")
        finally:
            del self._clients[client_id]

    async def _receive_loop(self):
        """客户端消息接收循环"""
        try:
            while self._running:
                try:
                    if not self._ws:
                        await asyncio.sleep(1)
                        continue

                    message = await self._ws.recv()
                    data = json.loads(message)

                    event = self._parse_server_message(data)
                    if event:
                        await self.emit_event(event)

                except websockets.exceptions.ConnectionClosed:
                    logger.info("[WebSocket] Connection closed")
                    if self.auto_reconnect and self._running:
                        self._schedule_reconnect()
                    break
                except asyncio.CancelledError:
                    logger.info("[WebSocket] Receive loop cancelled")
                    break
                except Exception as e:
                    logger.info(f"[WebSocket] Error in receive loop: {e}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("[WebSocket] Receive loop cancelled (outer)")
        finally:
            logger.info("[WebSocket] Receive loop ended")

    def _parse_client_message(self, data: Dict[str, Any], client_id: str) -> Optional[PlatformEvent]:
        """解析客户端消息（服务端模式）"""
        msg_type = data.get("type", "message")

        if msg_type != "message":
            return None

        content = MessageContent(
            text=data.get("text", ""),
            images=data.get("images", []),
            raw_content=data
        )

        sender = SenderInfo(
            id=client_id,
            name=data.get("sender_name", f"Client-{client_id}"),
            is_bot=False
        )

        return PlatformEvent(
            platform=PlatformType.WEBSOCKET,
            event_type=EventType.MESSAGE,
            sender=sender,
            content=content,
            raw_event=data,
            timestamp=datetime.now(),
            message_id=data.get("message_id")
        )

    def _parse_server_message(self, data: Dict[str, Any]) -> Optional[PlatformEvent]:
        """解析服务端消息（客户端模式）"""
        msg_type = data.get("type", "message")

        if msg_type != "message":
            return None

        content = MessageContent(
            text=data.get("text", ""),
            images=data.get("images", []),
            raw_content=data
        )

        sender = SenderInfo(
            id="server",
            name="Server",
            is_bot=False
        )

        return PlatformEvent(
            platform=PlatformType.WEBSOCKET,
            event_type=EventType.MESSAGE,
            sender=sender,
            content=content,
            raw_event=data,
            timestamp=datetime.now(),
            message_id=data.get("message_id")
        )

    async def parse_event(self, raw_event: Dict[str, Any]) -> Optional[PlatformEvent]:
        """解析原始事件"""
        if self.mode == "server":
            return self._parse_client_message(raw_event, "unknown")
        else:
            return self._parse_server_message(raw_event)

    async def send_message(self, target_id: str, content: MessageContent, **kwargs) -> bool:
        """发送消息"""
        message = {
            "type": "message",
            "text": content.text or "",
            "images": content.images or [],
            "timestamp": datetime.now().isoformat()
        }

        try:
            if self.mode == "server":
                # 服务端模式: 发送给指定客户端
                if target_id in self._clients:
                    await self._clients[target_id].send(json.dumps(message))
                    return True
                else:
                    # 广播给所有客户端
                    for client in self._clients.values():
                        await client.send(json.dumps(message))
                    return True
            else:
                # 客户端模式: 发送给服务端
                if self._ws:
                    await self._ws.send(json.dumps(message))
                    return True
            return False
        except Exception as e:
            logger.info(f"[WebSocket] Failed to send message: {e}")
            return False

    async def stop(self):
        """停止 WebSocket 适配器"""
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

        if self.mode == "server":
            # 关闭所有客户端连接
            for client in list(self._clients.values()):
                await client.close()
            self._clients.clear()

            # 关闭服务器
            if self._server:
                self._server.close()
                await self._server.wait_closed()
                logger.info("[WebSocket] Server stopped")
        else:
            # 客户端模式
            if self._ws:
                await self._ws.close()
                logger.info("[WebSocket] Client disconnected")
