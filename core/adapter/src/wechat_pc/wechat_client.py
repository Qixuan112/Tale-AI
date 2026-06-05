from __future__ import annotations

import asyncio
import functools
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal, Optional

MAX_MSG_ID_CACHE = 2000

from core.utils.logger import get_logger
from pathlib import Path

logger = get_logger("wechat_client")


def _get_project_root() -> Path:
    """计算项目根目录（wechat_client.py 位于 core/adapter/src/wechat_pc/）"""
    return Path(__file__).resolve().parents[4]


def _get_data_path() -> Path:
    return _get_project_root() / "data"

# wxauto: WeChat PC automation library (embedded)
# Source: https://github.com/cluic/wxauto
# License: Apache License 2.0 (see wxauto/LICENSE)
_import_error = None
try:
    from .wxauto import WeChat
    from .wxauto.elements import WxParam
except ImportError as e:
    WeChat = None
    WxParam = None
    _import_error = e
    logger.warning(f"wxauto import failed: {e}")
except Exception as e:
    WeChat = None
    WxParam = None
    _import_error = e
    logger.warning(f"wxauto import failed unexpectedly: {type(e).__name__}: {e}", exc_info=True)

# 强制锁定 wxauto 日志级别为 INFO，防止 WeChat.__init__ 中 set_debug(True) 再次打开 DEBUG 刷屏
try:
    import logging as _logging
    from .wxauto import utils as _wxauto_utils

    def _locked_set_debug(debug: bool):
        _wxauto_utils.wxlog.setLevel(_logging.INFO)
        _wxauto_utils.console_handler.setLevel(_logging.INFO)

    _wxauto_utils.set_debug = _locked_set_debug
    _wxauto_utils.wxlog.setLevel(_logging.INFO)
    _wxauto_utils.console_handler.setLevel(_logging.INFO)
except Exception:
    pass


class WeChatClientError(Exception):
    """包装层通用异常"""
    pass


class WindowLostError(WeChatClientError):
    """微信窗口丢失，需调用 connect() 重连"""
    pass


class SendTimeoutError(WeChatClientError):
    """发送超时（如剪贴板粘贴卡住）"""
    pass


@dataclass
class WeChatMessage:
    msg_id: str           # RuntimeId 拼接（临时，重启失效）
    session_name: str     # 聊天对象名（群名/好友备注/昵称）
    sender_name: str      # 发送者昵称
    sender_type: Literal["self", "friend", "sys", "time"]
    content: str          # 文本内容（图片/文件已被替换为本地路径）
    msg_type: Literal["text", "image", "file", "voice", "sys"]
    raw_control: Any      # 原始 uia 控件（如需二次操作）


class WeChatClient:
    def __init__(
        self,
        language: str = "cn",
        debug: bool = False,
        save_pic: bool = False,
        save_file: bool = False,
        save_voice: bool = False,
        self_nickname: str = "",
    ):
        self._language = language
        self._debug = debug
        self._save_pic = save_pic
        self._save_file = save_file
        self._save_voice = save_voice
        self._self_nickname = self_nickname

        self._wx: Optional[Any] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._local = threading.local()
        self._session_cache: list[str] = []
        self._group_cache: dict[str, Optional[bool]] = self._load_group_cache()
        self._connected = False
        self._last_msg_ids: dict[str, set[str]] = {}  # 各会话上次轮询的消息 id
        self._last_msg_fingerprints: dict[str, set[str]] = {}  # 各会话上次轮询的内容指纹（RuntimeId 失效时兜底去重）
        self._recent_fingerprints: dict[str, list[tuple[str, float]]] = {}  # 各会话最近见过的消息指纹，用于时间窗口去重

    @staticmethod
    def _group_cache_path() -> str:
        return os.path.join(str(_get_data_path()), "files", "wechat_pc", "group_cache.json")

    @classmethod
    def _load_group_cache(cls) -> dict[str, Optional[bool]]:
        path = cls._group_cache_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {k: v for k, v in data.items() if v is not None}
            except Exception as e:
                logger.warning(f"Failed to load group cache: {e}")
        return {}

    def _save_group_cache(self):
        path = self._group_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            # 只保存明确已知的结果（True/False），不保存 None
            valid_cache = {k: v for k, v in self._group_cache.items() if v is not None}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(valid_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save group cache: {e}")

    def _ensure_com_and_call(self, bound_method):
        """包装方法：确保 COM 已初始化后再调用 wxauto 方法"""
        if not getattr(self._local, "com_initialized", False):
            try:
                import pythoncom
                pythoncom.CoInitialize()
                self._local.com_initialized = True
            except Exception:
                try:
                    import ctypes
                    ctypes.windll.ole32.CoInitializeEx(None, 0x2)
                    self._local.com_initialized = True
                except Exception:
                    pass
        return bound_method()

    def _ensure_executor(self):
        """确保 ThreadPoolExecutor 处于可用状态，已关闭时重新创建"""
        if self._executor is None or getattr(self._executor, "_shutdown", False):
            if self._executor is not None:
                try:
                    self._executor.shutdown(wait=False)
                except Exception:
                    pass
            self._executor = ThreadPoolExecutor(max_workers=1)
            self._local = threading.local()
            logger.debug("[executor] Re-created ThreadPoolExecutor after shutdown")

    async def _wx_call(self, method, *args, timeout: float = 30.0, **kwargs):
        """在单线程执行器中调用同步 wxauto 方法"""
        if WeChat is None:
            raise WeChatClientError("wxauto is not available")
        if self._wx is None:
            raise WindowLostError("WeChat window not initialized, call connect() first")

        self._ensure_executor()

        # run_in_executor 不接受 kwargs，先用 partial 绑定
        bound = functools.partial(method, *args, **kwargs)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._executor, self._ensure_com_and_call, bound)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as e:
            raise SendTimeoutError(f"wxauto call timed out after {timeout}s") from e
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ("window", "hwnd", "找不到", "timeout")):
                self._connected = False
                raise WindowLostError(f"WeChat window lost: {e}") from e
            raise WeChatClientError(f"wxauto call failed: {e}") from e

    async def connect(self) -> None:
        """初始化微信窗口，支持重连"""
        global WeChat, WxParam
        self._ensure_executor()
        if WeChat is None:
            # 模块级别导入失败时，在运行时重试（此时 sys.path 已完整）
            try:
                from .wxauto import WeChat as _WeChat
                from .wxauto.elements import WxParam as _WxParam
                WeChat = _WeChat
                WxParam = _WxParam
                logger.info("wxauto imported successfully at runtime")
            except Exception as e:
                logger.error(f"wxauto import failed at runtime: {e}", exc_info=True)
                raise WeChatClientError(f"wxauto is not available on this platform: {e}") from e

        # 统一保存路径到 Tale data 目录，避免在工作目录创建 wxauto文件/
        if WxParam is not None:
            wechat_save_dir = os.path.join(str(_get_data_path()), "files", "wechat_pc")
            os.makedirs(wechat_save_dir, exist_ok=True)
            WxParam.DEFALUT_SAVEPATH = wechat_save_dir
            logger.debug(f"Set wxauto save path to: {wechat_save_dir}")

        def _init():
            # 线程池线程默认未初始化 COM，wxauto/UIA 需要 apartment-threaded COM
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 0x2)
            # 初始化期间强制关闭 wxauto debug，避免 GetAllMessage 加载历史消息时刷屏
            return WeChat(language=self._language, debug=False)

        # 首次初始化不走 _wx_call（因为 _wx_call 要求 self._wx 已存在）
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self._executor, _init)
        try:
            self._wx = await asyncio.wait_for(future, timeout=10.0)
            self._connected = True
            # 强制抑制 wxauto 内部库的 DEBUG 日志（格式与 KiraAI 不一致，且极冗长）
            import logging
            wxlog = logging.getLogger("wxauto")
            wxlog.setLevel(logging.INFO)
            for h in wxlog.handlers:
                h.setLevel(logging.INFO)
            logging.getLogger("wxauto.elements").setLevel(logging.INFO)
            logger.info("WeChat window connected successfully")
            # 初始化消息记录，避免首次轮询把历史消息当成新消息
            try:
                all_msgs = self._wx.GetAllMessage()
                current_chat = self._wx.CurrentChat()
                if all_msgs and current_chat:
                    current_ids = {getattr(m, "id", "") for m in all_msgs if getattr(m, "id", "")}
                    self._last_msg_ids[current_chat] = current_ids
                    # 同步初始化 wxauto 的 usedmsgid，避免 GetNextNewMessage 首次调用时
                    # 因 usedmsgid 为空而错误进入"获取其他窗口新消息"分支导致超时
                    self._wx.usedmsgid = [getattr(m, "id", "") for m in all_msgs if getattr(m, "id", "")]
                    logger.debug(f"[connect] Initialized {len(current_ids)} message ids for '{current_chat}'")
            except Exception as e:
                logger.debug(f"[connect] Failed to initialize message ids: {e}")
        except asyncio.TimeoutError as e:
            self._connected = False
            raise WeChatClientError("Failed to connect to WeChat window: timeout") from e
        except Exception as e:
            self._connected = False
            raise WeChatClientError(f"Failed to connect to WeChat window: {e}") from e

    async def is_alive(self) -> bool:
        """检测微信窗口是否仍存在且可操作"""
        if self._wx is None:
            return False
        try:
            result = await self._wx_call(
                lambda: self._wx.CurrentChat() is not None, timeout=5.0
            )
            return bool(result)
        except (WindowLostError, WeChatClientError):
            self._connected = False
            return False

    async def _download_media_for_msg(self, session_name: str, msg: Any) -> None:
        """对单条原始消息中的媒体文件进行下载，替换 content 为本地路径。"""
        content = getattr(msg, "content", "")
        if not content or not hasattr(msg, "control"):
            return

        # 中文微信的媒体标记前缀
        media_prefixes = {
            "pic": "[图片]",
            "file": "[文件]",
            "voice": "[语音]",
        }

        if self._save_pic and content.startswith(media_prefixes["pic"]):
            try:
                img_path = await self._wx_call(
                    self._wx._download_pic, msg.control, timeout=15.0
                )
                if img_path:
                    msg.content = img_path
                    if hasattr(msg, "info") and isinstance(msg.info, list) and len(msg.info) > 1:
                        msg.info[1] = img_path
                    logger.debug(f"[media] Downloaded pic for [{session_name}]: {img_path}")
            except Exception as e:
                logger.warning(f"[media] Failed to download pic for [{session_name}]: {e}")

        elif self._save_file and content.startswith(media_prefixes["file"]):
            try:
                file_path = await self._wx_call(
                    self._wx._download_file, msg.control, timeout=15.0
                )
                if file_path:
                    msg.content = file_path
                    if hasattr(msg, "info") and isinstance(msg.info, list) and len(msg.info) > 1:
                        msg.info[1] = file_path
                    logger.debug(f"[media] Downloaded file for [{session_name}]: {file_path}")
            except Exception as e:
                logger.warning(f"[media] Failed to download file for [{session_name}]: {e}")

        elif self._save_voice and content.startswith(media_prefixes["voice"]):
            try:
                voice_text = await self._wx_call(
                    self._wx._get_voice_text, msg.control, timeout=15.0
                )
                if voice_text:
                    msg.content = voice_text
                    if hasattr(msg, "info") and isinstance(msg.info, list) and len(msg.info) > 1:
                        msg.info[1] = voice_text
                    logger.debug(f"[media] Got voice text for [{session_name}]: {voice_text[:30]}...")
            except Exception as e:
                logger.warning(f"[media] Failed to get voice text for [{session_name}]: {e}")

    @staticmethod
    def _msg_fingerprint(session_name: str, msg: Any) -> str:
        """生成消息内容指纹，用于在 RuntimeId 不稳定时做去重。

        对语音/视频消息会去除播放状态后缀（如 ",未播放"、",已播放"），
        避免同一消息因状态变化而被误判为不同消息。
        """
        sender = getattr(msg, "sender", "")
        content = getattr(msg, "content", "")
        msg_type = getattr(msg, "type", "")

        # 去除语音/视频消息的状态后缀，提取核心标识
        if content:
            # 匹配 [语音]X秒,未播放 → [语音]X秒
            # 匹配 [视频],未播放 → [视频]
            if "," in content and ("语音" in content or "视频" in content):
                content = content.split(",")[0]

        # 使用 sender + content + type 的前 80 字作为指纹
        return f"{session_name}:{sender}:{msg_type}:{content[:80]}"

    def _is_recent_duplicate(self, session_name: str, fingerprint: str, window: float = 15.0) -> bool:
        """检查该指纹在最近 window 秒内是否已出现过。"""
        now = time.time()
        recent = self._recent_fingerprints.get(session_name, [])
        # 清理过期的记录
        recent = [(fp, ts) for fp, ts in recent if now - ts < window]
        self._recent_fingerprints[session_name] = recent
        return any(fp == fingerprint for fp, _ in recent)

    def _record_fingerprint(self, session_name: str, fingerprint: str):
        """记录一条消息的指纹和时间戳。"""
        now = time.time()
        if session_name not in self._recent_fingerprints:
            self._recent_fingerprints[session_name] = []
        self._recent_fingerprints[session_name].append((fingerprint, now))

    async def poll_messages(self, max_round: int = 5) -> dict[str, list[WeChatMessage]]:
        """轮询所有新消息，返回 {session_name: [messages]}"""
        if not self._connected:
            raise WindowLostError("WeChat client not connected")

        raw_messages: dict[str, list] = {}

        # 1) 首先尝试标准 GetNextNewMessage（能处理其他窗口的新消息）
        #    注意：不传 savepic/savefile/savevoice，避免 wxauto 内部下载阻塞
        get_next_ok = False
        for _ in range(max_round):
            try:
                newmsg = await self._wx_call(
                    self._wx.GetNextNewMessage,
                    savepic=False,
                    savefile=False,
                    savevoice=False,
                    timeout=6,
                )
            except Exception as e:
                logger.debug(f"GetNextNewMessage failed: {e}")
                break

            if not newmsg:
                break
            get_next_ok = True
            for session, msgs in newmsg.items():
                if session not in raw_messages:
                    raw_messages[session] = []
                for m in msgs:
                    fp = self._msg_fingerprint(session, m)
                    if self._is_recent_duplicate(session, fp):
                        continue
                    self._record_fingerprint(session, fp)
                    raw_messages[session].append(m)

        # 2) 回退：获取当前聊天所有消息，自己对比找出新消息
        #    （解决 GetNextNewMessage 因 RuntimeId 变化而漏检的问题）
        #    同样：不传 savepic/savefile/savevoice，避免反复下载历史图片
        try:
            current_chat = await self._wx_call(lambda: self._wx.CurrentChat(), timeout=5.0)
            all_msgs = await self._wx_call(
                self._wx.GetAllMessage,
                savepic=False,
                savefile=False,
                savevoice=False,
                timeout=10,
            )
            if all_msgs and current_chat:
                # 同步 wxauto 的 usedmsgid，避免其内部状态与当前消息列表脱节
                # 这是防止 GetNextNewMessage 下次调用时错误进入"获取其他窗口新消息"分支的关键
                try:
                    wxauto_ids = [getattr(m, "id", "") for m in all_msgs if getattr(m, "id", "")]
                    if wxauto_ids and self._wx is not None:
                        self._wx.usedmsgid = wxauto_ids
                        logger.debug(f"[poll] Synced wxauto usedmsgid ({len(wxauto_ids)} ids) for '{current_chat}'")
                except Exception as sync_e:
                    logger.debug(f"[poll] Failed to sync wxauto usedmsgid: {sync_e}")

                current_ids = {getattr(m, "id", "") for m in all_msgs if getattr(m, "id", "")}
                last_ids = self._last_msg_ids.get(current_chat)

                # 同时维护内容指纹集合，作为 RuntimeId 失效时的去重兜底
                current_fingerprints = {
                    self._msg_fingerprint(current_chat, m) for m in all_msgs
                }
                last_fps = self._last_msg_fingerprints.get(current_chat, set())

                if last_ids is None:
                    # 首次轮询该会话：只记录 id，不返回任何消息
                    self._last_msg_ids[current_chat] = current_ids
                    self._last_msg_fingerprints[current_chat] = current_fingerprints
                    logger.debug(f"[poll] First poll for '{current_chat}', recorded {len(current_ids)} msg ids, skipped")
                else:
                    # 双重去重：先用 RuntimeId，再用内容指纹兜底
                    new_msgs = []
                    for m in all_msgs:
                        mid = getattr(m, "id", "")
                        fp = self._msg_fingerprint(current_chat, m)
                        if mid and mid not in last_ids:
                            new_msgs.append(m)
                        elif fp not in last_fps and not mid:
                            new_msgs.append(m)

                    # 限制一次最多返回 10 条，避免消息风暴
                    if len(new_msgs) > 10:
                        logger.debug(f"[poll] Too many new msgs ({len(new_msgs)}), truncating to last 10")
                        new_msgs = new_msgs[-10:]

                    if new_msgs:
                        logger.debug(
                            f"[poll] Fallback: current chat '{current_chat}' has {len(new_msgs)} new msg(s) "
                            f"(total {len(all_msgs)}, last known {len(last_ids)})"
                        )
                        if current_chat not in raw_messages:
                            raw_messages[current_chat] = []
                        for m in new_msgs:
                            fp = self._msg_fingerprint(current_chat, m)
                            if self._is_recent_duplicate(current_chat, fp):
                                continue
                            self._record_fingerprint(current_chat, fp)
                            raw_messages[current_chat].append(m)

                    # 更新记录，限制集合大小防止内存泄漏
                    merged_ids = current_ids | last_ids
                    if len(merged_ids) > MAX_MSG_ID_CACHE:
                        merged_ids = set(list(merged_ids)[-MAX_MSG_ID_CACHE:])
                    self._last_msg_ids[current_chat] = merged_ids

                    merged_fps = current_fingerprints | last_fps
                    if len(merged_fps) > MAX_MSG_ID_CACHE:
                        merged_fps = set(list(merged_fps)[-MAX_MSG_ID_CACHE:])
                    self._last_msg_fingerprints[current_chat] = merged_fps
        except Exception as e:
            logger.debug(f"Fallback GetAllMessage failed: {e}")

        # 3) 对原始消息中的媒体文件进行下载（只下载本次识别出的新消息）
        if self._save_pic or self._save_file or self._save_voice:
            for session_name, msg_list in raw_messages.items():
                for msg in msg_list:
                    await self._download_media_for_msg(session_name, msg)

        total = sum(len(v) for v in raw_messages.values())
        if total > 0:
            logger.debug(f"[poll] Fetched {total} raw message(s) from {len(raw_messages)} session(s)")

        result: dict[str, list[WeChatMessage]] = {}
        for session_name, msg_list in raw_messages.items():
            result[session_name] = []
            for msg in msg_list:
                wechat_msg = self._convert_message(session_name, msg)
                if wechat_msg:
                    result[session_name].append(wechat_msg)
        return result

    def _convert_message(self, session_name: str, msg: Any) -> Optional[WeChatMessage]:
        """将 wxauto 原始消息转换为 WeChatMessage"""
        msg_type_str = getattr(msg, "type", "unknown")
        sender = getattr(msg, "sender", "unknown")
        content = getattr(msg, "content", "")
        msg_id = getattr(msg, "id", "")

        if msg_type_str == "sys":
            sender_type = "sys"
            parsed_msg_type = "sys"
        elif msg_type_str == "time":
            sender_type = "time"
            parsed_msg_type = "sys"
        elif msg_type_str == "self":
            sender_type = "self"
            parsed_msg_type = self._detect_content_type(content)
        elif msg_type_str == "friend":
            sender_type = "friend"
            parsed_msg_type = self._detect_content_type(content)
        else:
            sender_type = "friend"
            parsed_msg_type = self._detect_content_type(content)

        if msg_type_str == "friend":
            sender_name = getattr(msg, "sender", sender)
        else:
            sender_name = sender

        return WeChatMessage(
            msg_id=msg_id,
            session_name=session_name,
            sender_name=sender_name,
            sender_type=sender_type,
            content=content,
            msg_type=parsed_msg_type,
            raw_control=getattr(msg, "control", None),
        )

    @staticmethod
    def _detect_content_type(content: str) -> Literal["text", "image", "file", "voice"]:
        """根据内容判断消息类型"""
        if not content:
            return "text"
        if content.startswith("[图片]"):
            return "image"
        if content.startswith("[文件]"):
            return "file"
        if content.startswith("[语音]"):
            return "voice"
        # savepic/savefile 为 True 时，content 被替换为本地路径
        if os.path.isfile(content):
            ext = os.path.splitext(content)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
                return "image"
            if ext in (".mp3", ".wav", ".ogg", ".m4a", ".amr"):
                return "voice"
            return "file"
        return "text"

    async def send_text(self, who: str, text: str, at: Optional[list[str]] = None) -> bool:
        """发送文本消息，who 为聊天对象名"""
        await self._wx_call(self._wx.SendMsg, text, who=who, at=at, timeout=30.0)
        return True

    async def send_files(self, who: str, file_paths: list[str]) -> bool:
        """发送文件/图片（通过剪贴板粘贴）"""
        valid_paths = [p for p in file_paths if os.path.exists(p)]
        if not valid_paths:
            logger.warning("No valid files to send")
            return False

        result = await self._wx_call(
            self._wx.SendFiles, valid_paths, who=who, timeout=60.0
        )
        return bool(result)

    async def get_session_list(self, force_refresh: bool = False) -> list[str]:
        """获取当前聊天列表，带本地缓存"""
        if not force_refresh and self._session_cache:
            return self._session_cache.copy()

        session_dict = await self._wx_call(self._wx.GetSessionList, timeout=10.0)
        self._session_cache = list(session_dict.keys())
        return self._session_cache.copy()

    async def is_group_chat(self, session_name: str) -> Optional[bool]:
        """判断是否为群聊（启发式 + 缓存）。None 表示无法判断"""
        if session_name in self._group_cache:
            cached = self._group_cache[session_name]
            # None 表示上次探测失败，允许重试
            if cached is not None:
                return cached

        try:
            await self._wx_call(self._wx.ChatWith, session_name, timeout=10.0)
            members = await self._wx_call(self._wx.GetGroupMembers, timeout=5.0)
            is_group = bool(members) and len(members) > 0
            self._group_cache[session_name] = is_group
            self._save_group_cache()
            return is_group
        except Exception:
            # 探测失败时不缓存，让下次有机会重试
            self._group_cache.pop(session_name, None)
            return None

    async def close(self) -> None:
        """清理 ThreadPoolExecutor 等资源"""
        self._connected = False
        self._executor.shutdown(wait=False)
        logger.info("WeChat client closed")

    async def get_moments_feed(self, count: int = 10) -> list[dict]:
        """打开朋友圈并抓取内容列表"""
        prev_chat = None
        try:
            # 记录当前窗口，便于恢复
            try:
                prev_chat = await self._wx_call(lambda: self._wx.CurrentChat(), timeout=5.0)
            except Exception:
                pass

            await self._wx_call(lambda: self._wx.A_MomentsIcon.Click(), timeout=10.0)

            # 智能等待：最多 5 秒，每 300ms 检查列表是否已加载
            for _ in range(17):  # ~5.1s
                await asyncio.sleep(0.3)
                children = await self._wx_call(
                    lambda: self._wx.ChatBox.ListControl().GetChildren(), timeout=5.0
                )
                if children and len(children) > 0:
                    break

            raw_items = await self._wx_call(self._scrape_moments_feed_impl, timeout=15.0)

            # 恢复之前窗口
            if prev_chat:
                try:
                    await self._wx_call(self._wx.ChatWith, prev_chat, timeout=5.0)
                except Exception:
                    pass

            return raw_items[:count]
        except Exception as e:
            logger.warning(f"Failed to fetch WeChat Moments feed: {e}")
            return []

    def _scrape_moments_feed_impl(self) -> list[dict]:
        """抓取朋友圈列表并返回结构化动态列表

        通过 UIA 子控件深度解析，识别每条动态的：
        - 发送者（区分好友/自己）
        - 文本内容
        - 时间戳
        - 媒体类型（图片/视频）
        """
        posts = []
        own_nickname = getattr(self._wx, "nickname", "") or ""
        try:
            moments_list = self._wx.ChatBox.ListControl()
            controls = moments_list.GetChildren()
            for idx, element in enumerate(controls):
                # 跳过非 ListItemControl
                if element.ControlTypeName != 'ListItemControl':
                    continue

                content = element.Name.strip()
                if not content:
                    continue

                user_name = ""
                user_id = ""
                text_content = ""
                timestamp = ""
                media_type = None
                is_self_post = False

                try:
                    children = element.GetChildren()

                    # 分类子控件
                    buttons = [c for c in children if c.ControlTypeName == 'ButtonControl']
                    texts = [c for c in children if c.ControlTypeName == 'TextControl']
                    images = [c for c in children if c.ControlTypeName == 'ImageControl']

                    # --- 发送者识别 ---
                    # 用头像 ButtonControl 的位置判断左侧（好友）还是右侧（自己）
                    item_rect = element.BoundingRectangle
                    item_mid_x = (item_rect.left + item_rect.right) / 2

                    if buttons:
                        first_btn = buttons[0]
                        btn_rect = first_btn.BoundingRectangle
                        # 头像在右侧 → 自己的动态
                        if btn_rect.left >= item_mid_x:
                            is_self_post = True

                    if is_self_post:
                        user_name = own_nickname or "我"
                        # 自己的动态：第一个 TextControl 通常是正文
                        if texts:
                            text_content = texts[0].Name.strip()
                    else:
                        # 好友的动态：TextControl 依次为：昵称、正文、时间/位置
                        for t in texts:
                            t_name = t.Name.strip()
                            if not t_name:
                                continue
                            if not user_name:
                                # 第一个非空 TextControl 作为昵称
                                user_name = t_name
                            elif not text_content:
                                # 第二个作为正文
                                text_content = t_name
                            else:
                                # 后续文本作为时间/位置信息
                                if not timestamp:
                                    timestamp = t_name

                    # --- 媒体类型检测 ---
                    if images:
                        media_type = "image"
                    # 如果有 ButtonControl 且其 Name 包含图片/视频标记
                    for btn in buttons:
                        btn_name = btn.Name.strip()
                        if btn_name in ("图片", "视频", "image", "video"):
                            media_type = btn_name
                            break

                    # --- 时间戳提取（从 element.Name 中尝试提取时间模式） ---
                    if not timestamp:
                        # 常见微信朋友圈时间格式：刚刚、X分钟前、X小时前、昨天 HH:MM、MM-dd HH:MM
                        import re as _re
                        time_patterns = [
                            r'(刚刚)',
                            r'(\d+分钟前)',
                            r'(\d+小时前)',
                            r'(昨天\s*\d{1,2}:\d{2})',
                            r'(\d{1,2}-\d{1,2}\s*\d{1,2}:\d{2})',
                            r'(\d{4}-\d{1,2}-\d{1,2})',
                        ]
                        for pat in time_patterns:
                            m = _re.search(pat, content)
                            if m:
                                timestamp = m.group(1)
                                break

                except Exception:
                    # 子控件解析失败时回退到 element.Name
                    user_name = own_nickname or ""
                    text_content = content

                # 保障至少有一个非空文本
                final_text = text_content or content

                # 使用下标生成稳定 ID（element.Name 带时间戳使 ID 具有辨识度）
                post_id = f"moments_{int(time.time()*1000)}_{idx}"

                post = {
                    "id": post_id,
                    "user_name": user_name or own_nickname or "",
                    "user_id": user_id,
                    "text": final_text,
                    "timestamp": timestamp,
                    "media_type": media_type,
                    "_is_self": is_self_post,
                }
                posts.append(post)

        except Exception:
            logger.warning("Failed to scrape moments feed", exc_info=True)
        return posts
