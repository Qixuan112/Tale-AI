import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional, Callable, Awaitable

try:
    import websockets
except ImportError:
    websockets = None

from ....utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# WebSocket 版本兼容包装
# ---------------------------------------------------------------------------

def _ws_connect(uri, *, extra_headers, **kwargs):
    """兼容新旧版 websockets 库的 connect 包装。

    新版（>=13）使用 ``additional_headers``，旧版使用 ``extra_headers``。
    """
    return websockets.connect(uri, extra_headers=extra_headers, **kwargs)


try:
    import websockets.asyncio.client

    if websockets.connect is websockets.asyncio.client.connect:
        def _ws_connect(uri, *, extra_headers, **kwargs):
            return websockets.connect(
                uri, additional_headers=extra_headers, **kwargs
            )
except ImportError:
    pass


# ---------------------------------------------------------------------------
# NapCatWebSocketClient
# ---------------------------------------------------------------------------

class NapCatWebSocketClient:
    """NapCat QQ WebSocket 底层通信客户端。

    职责
    ----
    * WebSocket 连接建立／断开／重连（指数退避）
    * echo + Future 请求-响应匹配（``send_action``）
    * 被动心跳检测（监听 NapCat 服务端推送的 heartbeat meta_event）
    * 登录验证（连接后调用 ``get_login_info`` 比对 bot_uin）
    * 消息透传：收到的非 API-响应消息通过 callback 抛给上层

    典型用法
    --------
    .. code:: python

        client = NapCatWebSocketClient()
        client.set_message_callback(on_message)
        ok = await client.run(bot_uin="123456",
                              ws_url="ws://localhost:3001",
                              access_token="...")
        if ok:
            ...  # 使用 client.send_action() 发送 API 请求
    """

    def __init__(self):
        self.websocket = None
        self.self_id: Optional[str] = None

        # echo → Future，用于请求-响应匹配
        self.response_futures: dict[str, asyncio.Future] = {}

        # 事件
        self.login_success_event: asyncio.Event = asyncio.Event()
        self.shutdown_event: asyncio.Event = asyncio.Event()

        # run() 完成时通过此 Future 回传结果（供 adapter.start() 等待）
        self._run_done: Optional[asyncio.Future[bool]] = None

        # 任务引用
        self._listening_task: Optional[asyncio.Task] = None

        # 心跳检测
        self.last_heartbeat: Optional[int] = None
        self._heartbeat_watchdog_task: Optional[asyncio.Task] = None

        # send_action 快速路径标志
        self._send_ready: bool = False

        # 消息回调（由 QQAdapter 注入）
        self._message_callback: Optional[Callable[[dict], Awaitable[None]]] = None

        # 配置
        self._ws_url: str = ""
        self._access_token: str = ""

    # ── callback ──────────────────────────────────────────────────────

    def set_message_callback(self, callback: Callable[[dict], Awaitable[None]]):
        """注册消息回调，收到非 API-响应的消息时触发。"""
        self._message_callback = callback

    # ── 连接 ──────────────────────────────────────────────────────────

    async def connect(self) -> dict:
        """建立 WebSocket 连接。

        Returns
        -------
        {"status": "ok"} / {"status": "failed", "message": "..."}
        """
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        logger.info(f"连接到 {self._ws_url}")
        try:
            self.websocket = await _ws_connect(
                self._ws_url,
                extra_headers=headers,
                max_size=2**24,
                open_timeout=5.0,
                ping_timeout=10.0,
            )
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"连接失败: {e}")
            self.websocket = None
            return {"status": "failed", "message": str(e)}

    # ── 运行（完整启动流程） ──────────────────────────────────────────

    async def run(
        self,
        bot_uin: str,
        ws_url: str,
        access_token: Optional[str] = None,
    ) -> bool:
        """完整启动流程：连接 → 验证登录 → 开始监听。

        Parameters
        ----------
        bot_uin : str
            配置的机器人 QQ 号，用于登录验证。
        ws_url : str
            WebSocket 服务端地址。
        access_token : str, optional
            访问令牌。

        Returns
        -------
        bool
            True 表示启动成功，False 表示失败。
        """
        if websockets is None:
            logger.error("websockets 库未安装，请执行 pip install websockets")
            return False

        self.self_id = bot_uin
        self._ws_url = ws_url
        self._access_token = access_token or ""

        # 创建 run_done Future 供 adapter.start() 等待
        loop = asyncio.get_running_loop()
        self._run_done = loop.create_future()

        conn_resp = await self.connect()
        if conn_resp.get("status") != "ok":
            self._run_done.set_result(False)
            return False

        # 启动心跳 watchdog
        self._heartbeat_watchdog_task = asyncio.create_task(self._heartbeat_watchdog())

        # 启动消息监听（内部 while 循环处理重连）
        self._listening_task = asyncio.create_task(self._listen_loop())

        # 验证 bot_uin 是否匹配（直接用 get_login_info，不依赖 lifecycle）
        login_info = await self.send_action("get_login_info", {})
        if not login_info:
            logger.error("获取登录信息失败")
            await self.close()
            self._run_done.set_result(False)
            return False

        data = login_info.get("data") or {}
        logged_in_uin = str(data.get("user_id", ""))
        if logged_in_uin != bot_uin:
            logger.error(
                f"配置的账号 {bot_uin} 与 NapCat 登录账号 {logged_in_uin} 不一致"
            )
            await self.close()
            self._run_done.set_result(False)
            return False

        logger.info(f"账号验证通过: {bot_uin}")
        self._send_ready = True
        self._run_done.set_result(True)
        return True

    # ── 重连 ──────────────────────────────────────────────────────────

    async def _reconnect(self) -> bool:
        """指数退避重连，最多 20 次。

        Returns
        -------
        bool
            True 表示重连成功。
        """
        attempt = 0
        while not self.shutdown_event.is_set() and attempt < 20:
            attempt += 1
            logger.warning(f"WebSocket 连接断开，正在尝试第 {attempt} 次重连")
            resp = await self.connect()
            if resp.get("status") == "ok":
                logger.info("WebSocket 重连成功")
                return True
            delay = min(2**attempt, 60)
            logger.warning(
                f"重连失败 ({resp.get('message')}), "
                f"{delay} 秒后重试"
            )
            await asyncio.sleep(delay)
        logger.error("重连次数达到上限，WebSocket 重连失败！")
        return False

    # ── 消息接收 ──────────────────────────────────────────────────────

    async def _listen_loop(self):
        """统一消息接收主循环，内部处理重连。"""
        while not self.shutdown_event.is_set():
            try:
                ws = self.websocket
                if ws is None:
                    ok = await self._reconnect()
                    if not ok:
                        break
                    ws = self.websocket

                async for message in ws:
                    self._process_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket 连接已关闭")
                continue  # 回到循环头部，触发重连
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"消息监听异常: {e}", exc_info=True)
                break

    def _process_message(self, message: str):
        """同步处理收到的 WebSocket 消息（纯 CPU，无 await）。"""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"收到非 JSON 消息: {message[:200]}")
            return

        # 必须先处理 API 响应（同步），再回调上层
        echo = data.get("echo")
        if echo and echo in self.response_futures:
            future = self.response_futures.pop(echo)
            if not future.cancelled():
                future.set_result(data)
            return

        # 心跳检测
        if data.get("post_type") == "meta_event":
            if data.get("meta_event_type") == "heartbeat":
                self.last_heartbeat = data.get("time")
            elif data.get("meta_event_type") == "lifecycle":
                # lifecycle 仅日志，不再作为登录就绪信号
                logger.info("收到 lifecycle 事件: %s", data.get("sub_type", ""))

        # 抛给上层回调（用 create_task 避免阻塞消息接收）
        if self._message_callback:
            task = asyncio.create_task(self._message_callback(data))
            task.add_done_callback(
                lambda t: logger.error(
                    "消息回调异常: %s", t.exception()
                ) if t.exception() else None
            )

    # ── 心跳 watchdog ────────────────────────────────────────────────

    async def _heartbeat_watchdog(self):
        """如果超过 30 秒未收到心跳，主动断开重连。"""
        while not self.shutdown_event.is_set():
            await asyncio.sleep(30)
            if self.last_heartbeat is not None and not self.shutdown_event.is_set():
                # 检查最后心跳时间
                now = int(datetime.now().timestamp())
                if now - self.last_heartbeat > 35:
                    logger.warning("心跳超时，主动断开 WebSocket 触发重连")
                    if self.websocket:
                        await self.websocket.close()
                        self.websocket = None

    # ── API 调用 ──────────────────────────────────────────────────────

    async def send_action(
        self, action: str, params: dict = None, timeout: float = 10.0
    ) -> Optional[dict]:
        """发送 OneBot API 请求并等待响应。

        Parameters
        ----------
        action : str
            动作名，如 ``get_group_member_list``。
        params : dict, optional
            参数字典。
        timeout : float
            超时秒数。

        Returns
        -------
        响应 dict，超时或失败返回 None。
        """
        if not self.websocket:
            logger.warning("WebSocket 未连接，无法发送 API 请求")
            return None

        # 等待首次可用（最多 10 秒，后续不再等待）
        if not self._send_ready:
            # 如果 websocket 已连接但尚未标记就绪（run() 正在验证登录），
            # 直接放行，避免与 _run_done 形成死锁
            if self.websocket is None:
                try:
                    await asyncio.wait_for(self._run_done, timeout=10)
                except (asyncio.TimeoutError, asyncio.InvalidStateError):
                    logger.error("send_action 失败: 尚未就绪")
                    return None

        echo = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self.response_futures[echo] = future

        request = {
            "action": action.lstrip("/"),
            "params": params or {},
            "echo": echo,
        }

        try:
            await self.websocket.send(json.dumps(request))
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"API 请求 {action} 超时")
            self.response_futures.pop(echo, None)
            return None
        except Exception as e:
            logger.warning(f"API 请求 {action} 失败: {e}")
            self.response_futures.pop(echo, None)
            return None

    async def get_login_info(self) -> Optional[dict]:
        """获取当前登录信息。"""
        return await self.send_action("get_login_info", {})

    # ── 关闭 ──────────────────────────────────────────────────────────

    async def close(self):
        """关闭客户端，清理所有资源。"""
        self.shutdown_event.set()
        self.login_success_event.clear()

        # 清除所有 pending 的 API 请求 Future
        for echo, future in self.response_futures.copy().items():
            if not future.done():
                future.cancel()
            del self.response_futures[echo]

        if self._heartbeat_watchdog_task and not self._heartbeat_watchdog_task.done():
            self._heartbeat_watchdog_task.cancel()
            try:
                await self._heartbeat_watchdog_task
            except asyncio.CancelledError:
                pass

        if self._listening_task and not self._listening_task.done():
            self._listening_task.cancel()
            try:
                await self._listening_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        # 标记 run_done（防止 adapter.start() 永久等待）
        if self._run_done and not self._run_done.done():
            self._run_done.set_result(False)

        logger.info(f"账号 {self.self_id} 的连接已关闭")
