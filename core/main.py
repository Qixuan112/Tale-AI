import sys
import time
import threading
import asyncio
import signal
from pathlib import Path
from typing import Optional, Callable, Any, List, Dict

from .spin_think import spinning_think
from .bus import NextBus, bus
from .llm import ChatLLM, get_planllm, ToolLLM, get_vlm_llm
from .config.provide import (
    get_chat_api_key, get_chat_model, get_chat_url,
    get_plan_api_key, get_plan_model, get_plan_url,
)
from .config import MAX_SPLIT_COUNT
from .config.provide import config_loader
from .parse_xml import parse_xml_msg, format_message_for_display
from .function_caller import handle_function_call, parse_function_call, execute_function
from .adapter import (
    AdapterManager,
    AdapterEventBridge,
    PlatformEvent,
    MessageProcessor,
    ProcessorConfig,
    ProcessedMessage,
    ResponseDecision,
    PlatformConfigBuilder,
)
from .utils import get_logger

logger = get_logger(__name__)


def calculate_split_interval(text_length: int) -> float:
    """
    模拟真人打字的发送延迟。
    延迟 = max(字数 * 打字速度(ms/字) / 1000, 最小延迟)
    """
    bot = config_loader.bot.bot
    speed_ms = getattr(bot, 'typing_speed', 200.0)
    min_delay = getattr(bot, 'typing_min_delay', 2.0)
    delay = max(text_length * speed_ms / 1000.0, min_delay)
    return round(delay, 2)


class TaleCore:
    """Tale 核心应用类

    整合 LLM 对话、工具调用和适配器系统，支持多平台接入。

    架构分层：
    1. Application Layer (TaleCore): 应用核心，协调各模块
    2. Message Processor Layer: 消息处理（权限、唤醒词、决策）
    3. Adapter Bridge Layer: 适配器事件桥接
    4. Adapter Manager Layer: 适配器生命周期管理
    5. Platform Adapter Layer: 具体平台适配器实现
    """

    def __init__(self):
        self.chat: Optional[ChatLLM] = None
        self.toolllm: Optional[ToolLLM] = None
        self.adapter_bridge: Optional[AdapterEventBridge] = None
        self.message_processor: Optional[MessageProcessor] = None
        self.plugin_manager: Optional[Any] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._llm_executor = None
        self._chat_context_buffer: Dict[str, list] = {}
        self._name_to_id: Dict[str, Dict[str, str]] = {}

    def initialize(self):
        """初始化核心组件（幂等，可多次调用）"""
        if self.chat is not None:
            return

        import concurrent.futures
        self._llm_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="llm"
        )

        self.chat = self._init_chatllm()
        self.toolllm = self._init_toolllm()

        # 初始化消息处理器（从配置加载）
        self._init_message_processor()

        # 初始化适配器桥接器
        self.adapter_bridge = AdapterEventBridge(bus, config_loader)
        self.adapter_bridge.initialize()

        # 注册事件处理器
        self._register_event_handlers()

        # 注册 wechat_moments 专属处理器
        bus.on("wechat_moments_message", self._handle_wechat_moments_message)

        # 监听配置热重载事件
        bus.on("config_reloaded", self._on_config_reloaded)

        # 初始化插件管理器
        self._init_plugin_manager()

        logger.info("核心组件初始化完成")

    @staticmethod
    def _init_chatllm():
        api_key = get_chat_api_key()
        model = get_chat_model()
        url = get_chat_url()
        if not api_key:
            logger.warning("ChatLLM 未配置 API Key，请通过 WebUI 配置服务商")
            return None
        try:
            return ChatLLM(api_key=api_key, model=model, url=url)
        except Exception as e:
            logger.warning("ChatLLM 初始化失败: %s", e)
            return None

    @staticmethod
    def _init_toolllm():
        api_key = get_plan_api_key()
        model = get_plan_model()
        url = get_plan_url()
        if not api_key:
            logger.warning("ToolLLM 未配置 API Key，请通过 WebUI 配置服务商")
            return None
        try:
            return ToolLLM(api_key=api_key, model=model, url=url)
        except Exception as e:
            logger.warning("ToolLLM 初始化失败: %s", e)
            return None

    def _on_config_reloaded(self, event_data=None):
        if self.chat is None:
            self.chat = self._init_chatllm()
            if self.chat is not None:
                logger.info("ChatLLM 热重载初始化成功")
        if self.toolllm is None:
            self.toolllm = self._init_toolllm()
            if self.toolllm is not None:
                logger.info("ToolLLM 热重载初始化成功")
        if self.toolllm is not None:
            self.toolllm.rebuild_tool_definitions()

        # 重新初始化消息处理器（唤醒词、权限等配置可能已变更）
        self._init_message_processor()
        logger.info("MessageProcessor 已热重载")

    def _init_message_processor(self):
        """初始化消息处理器"""
        # 从配置构建处理器配置
        qq_config = config_loader.adapters.qq
        wake_config = config_loader.bot.wake
        if qq_config.enabled:
            processor_config = PlatformConfigBuilder.from_qq_config(
                qq_config,
                global_waking_keywords=wake_config.waking_keywords,
                enable_keyword_wake=wake_config.enable_keyword_wake,
                enable_quote_wake=wake_config.enable_quote_wake,
            )
            self.message_processor = MessageProcessor(processor_config)
            logger.info("消息处理器已初始化 (模式: %s)", processor_config.permission_mode)
        else:
            # 默认配置
            self.message_processor = MessageProcessor()
            logger.info("消息处理器已初始化 (默认配置)")

    def _register_event_handlers(self):
        """注册事件总线处理器"""
        # 监听平台消息事件
        bus.on("platform_message", self._handle_platform_message)
        bus.on("private_message", self._handle_private_message)
        bus.on("group_message", self._handle_group_message)
        bus.on("qq_message", self._handle_qq_message)
        bus.on("platform_notice", self._handle_platform_notice)

    def _init_plugin_manager(self):
        """初始化插件管理器 — 扫描 core/plugins/ + plugins/ (旧) + data/custom_plugins/"""
        try:
            from .plugin import PluginManager

            project_root = Path(__file__).parent.parent
            plugins_config = getattr(config_loader, "_plugins_config", {})

            # 主目录：core/plugins/（内置插件新位置）
            self.plugin_manager = PluginManager(
                plugins_dir=project_root / "core" / "plugins",
                config=plugins_config,
            )

            # 自定义插件目录：data/custom_plugins/
            custom_dir = project_root / "data" / "custom_plugins"
            if custom_dir.exists():
                self.plugin_manager._scan_plugins(custom_dir)

            self.plugin_manager.load_all_enabled()

            # 插件可能注册了新工具，刷新工具定义
            if self.toolllm is not None:
                self.toolllm.rebuild_tool_definitions()

            # 延迟注入提示词段（需要 ChatLLM/ToolLLM 引用）
            self.plugin_manager._wire_prompt_sections(
                chatllm=self.chat,
                toollLM=self.toolllm,
            )
            logger.info(
                "插件管理器初始化完成，已加载 %d 个插件",
                len(self.plugin_manager.list_loaded()),
            )
        except Exception as e:
            logger.warning("插件管理器初始化失败（不影响核心运行）: %s", e)

    def _handle_platform_message(self, event_data: dict):
        """处理平台消息事件（调试用）"""
        platform = event_data.get("platform", "unknown")
        sender_name = event_data.get("sender", {}).get("name", "Unknown")
        content = event_data.get("content", {})
        text = content.get("text", "")

        logger.debug("[平台消息] [%s] %s: %s", platform, sender_name, text)

    async def _handle_private_message(self, event_data: dict):
        """处理私聊消息"""
        await self._process_message_event(event_data)

    async def _handle_group_message(self, event_data: dict):
        """处理群消息"""
        await self._process_message_event(event_data)

    def _handle_qq_message(self, event_data: dict):
        """处理 QQ 特定消息"""
        # 可以在这里添加 QQ 特定的处理逻辑
        pass

    async def _handle_platform_notice(self, event_data: dict):
        """处理平台通知事件（戳一戳、入群、禁言等）"""
        try:
            text = event_data.get("content", {}).get("text", "")
            if text:
                logger.info("[通知] %s", text)
        except Exception as e:
            logger.debug("[通知] 处理通知事件时出错: %s", e)

    async def _handle_wechat_moments_message(self, event_data: dict):
        """处理微信朋友圈消息

        朋友圈动态走 `wechat_moments_message` 通道到达事件总线，
        此处将朋友圈事件转换为消息处理流程，让 LLM 层能感知朋友圈动态。
        """
        await self._process_moments_event(event_data)

    async def _process_moments_event(self, event_data: dict):
        """处理微信朋友圈动态事件

        朋友圈动态来自 WeChat PC 适配器的轮询，此处将其作为
        普通消息输入给 LLM，让 AI 能感知到朋友圈内容。

        当前接收到的朋友圈事件已包含结构化字段：
        - sender.name: 发布者昵称（已正确区分好友/自己）
        - content.text: 正文内容
        - raw_event.timestamp: 发布时间
        - raw_event.media_type: 媒体类型（如有）
        """
        try:
            platform = event_data.get("platform", "wechat_moments")
            sender = event_data.get("sender", {})
            content = event_data.get("content", {})
            text = content.get("text", "")
            sender_name = sender.get("name", "Unknown")

            # 从 raw_event 提取额外结构化信息
            raw = event_data.get("raw_event", {})
            timestamp = raw.get("timestamp", "") if isinstance(raw, dict) else ""
            media_type = raw.get("media_type", "") if isinstance(raw, dict) else ""

            if not text:
                logger.debug("[朋友圈] 跳过空内容动态 (发布者: %s)", sender_name)
                return

            # 构建带结构化信息的日志
            media_tag = f" [{media_type}]" if media_type else ""
            time_tag = f" ({timestamp})" if timestamp else ""
            logger.info(
                "[朋友圈] %s%s: %s%s",
                sender_name, media_tag, text[:80], time_tag,
            )

            # 构建用户输入，包含更多结构化信息
            extra_info = ""
            if timestamp:
                extra_info += f" [时间: {timestamp}]"
            if media_type:
                extra_info += f" [媒体: {media_type}]"
            user_input = f"[朋友圈动态] {sender_name}: {text}{extra_info}"

            chatllm_reply = await self._call_chatllm(user_input)
            # 朋友圈动态不需要发送回复（仅让 LLM 记录到记忆中）
            logger.info("[朋友圈] LLM 已处理 %s 的动态", sender_name)
        except Exception as e:
            logger.error("[朋友圈] 处理朋友圈事件时出错: %s", e, exc_info=True)

    async def _process_message_event(self, event_data: dict):
        """处理消息事件（使用 MessageProcessor 进行决策）

        Args:
            event_data: 事件数据（来自 AdapterEventBridge）
        """
        # 1. 从事件数据重建 PlatformEvent（简化版本）
        platform_event = self._reconstruct_platform_event(event_data)
        if not platform_event:
            return

        # 2. 获取来源适配器实例名（同类多实例时精确路由到正确的那个）
        adapter_instance = event_data.get("adapter_instance")

        # 3. 使用 MessageProcessor 处理消息
        processed = self.message_processor.process(platform_event)

        # 3.5 将消息存入上下文缓冲区（无论决策如何都记录）
        self._store_to_context_buffer(processed)

        # 4. 根据决策处理
        if processed.decision == ResponseDecision.RESPOND:
            await self._handle_respond_message(processed, adapter_instance=adapter_instance)
        elif processed.decision == ResponseDecision.SILENT:
            logger.debug("静默 %s: %s", processed.reason, processed.sender_name)
        else:
            # IGNORE - 忽略，但可以记录日志
            pass

    def _reconstruct_platform_event(self, event_data: dict) -> Optional[PlatformEvent]:
        """从事件数据重建 PlatformEvent

        Args:
            event_data: 事件数据

        Returns:
            PlatformEvent 或 None
        """
        try:
            from .adapter.event import PlatformType, EventType, MessageContent, SenderInfo
            from datetime import datetime

            platform = PlatformType(event_data.get("platform", "unknown"))
            event_type = EventType(event_data.get("event_type", "unknown"))

            sender_data = event_data.get("sender", {})
            sender = SenderInfo(
                id=sender_data.get("id", ""),
                name=sender_data.get("name", "Unknown"),
                avatar=sender_data.get("avatar"),
                is_bot=sender_data.get("is_bot", False),
            )

            content_data = event_data.get("content", {})
            content = MessageContent(
                text=content_data.get("text"),
                images=content_data.get("images", []),
                at_targets=content_data.get("at_targets", []),
                reply_to=content_data.get("reply_to"),
                reply_text=content_data.get("reply_text"),
                faces=content_data.get("faces", []),
                stickers=content_data.get("stickers", []),
                videos=content_data.get("videos", []),
                voices=content_data.get("voices", []),
                json_cards=content_data.get("json_cards", []),
            )

            timestamp_str = event_data.get("timestamp")
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()

            return PlatformEvent(
                platform=platform,
                event_type=event_type,
                sender=sender,
                content=content,
                message_id=event_data.get("message_id"),
                group_id=event_data.get("group_id"),
                group_name=event_data.get("group_name"),
                timestamp=timestamp,
                raw_event=event_data.get("raw_event", {}),
            )
        except Exception as e:
            logger.error("重建 PlatformEvent 失败: %s", e)
            return None

    def _store_to_context_buffer(self, processed: ProcessedMessage):
        """将消息存入上下文缓冲区，用于滑动窗口上下文。"""
        key = processed.group_id or processed.sender_id
        if not key or not processed.text:
            return
        if key not in self._chat_context_buffer:
            self._chat_context_buffer[key] = []
        import time
        self._chat_context_buffer[key].append({
            "sender": processed.sender_name,
            "text": processed.text,
            "time": time.strftime("%H:%M"),
            "images": list(getattr(processed, "images", []) or []),
        })
        # 限制缓冲区大小，防止内存泄漏
        if len(self._chat_context_buffer[key]) > 100:
            self._chat_context_buffer[key] = self._chat_context_buffer[key][-100:]

    def _download_ctx_image(self, url_or_path: str) -> Optional[str]:
        """下载上下文窗口中的图片到本地临时目录。

        如果是本地路径直接返回；远程 URL 下载到 data/temp/ctx_images/。
        """
        local_path = Path(url_or_path)
        if local_path.is_file():
            return str(local_path.resolve())

        if not url_or_path.startswith(('http://', 'https://')):
            return None

        # SSRF 防护
        from core.tools.network_safety import validate_url
        ssrf_error = validate_url(url_or_path)
        if ssrf_error:
            logger.warning("SSRF 安全检查未通过，跳过图片下载: %s", ssrf_error)
            return None

        import hashlib
        import os
        try:
            import requests
        except ImportError:
            return None

        # 生成缓存文件名
        ext = os.path.splitext(url_or_path.split('?')[0])[1] or '.jpg'
        name = hashlib.md5(url_or_path.encode()).hexdigest() + ext
        cache_dir = Path(__file__).parent.parent / "data" / "temp" / "ctx_images"
        cache_dir.mkdir(parents=True, exist_ok=True)
        dest = cache_dir / name

        if dest.is_file():
            return str(dest)

        try:
            resp = requests.get(url_or_path, timeout=10, stream=True)
            resp.raise_for_status()
            content_length = resp.headers.get('content-length')
            if content_length and int(content_length) > 5 * 1024 * 1024:
                logger.warning("图片过大，跳过下载: %s (%s)", url_or_path, content_length)
                return None
            with open(dest, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return str(dest)
        except Exception as e:
            logger.warning("下载上下文图片失败 %s: %s", url_or_path, e)
            return None

    async def _build_context_window(self, processed: ProcessedMessage, window: int) -> str:
        """从缓冲区获取最近 N 条消息作为上下文，图片自动 VLM 识别。

        排除缓冲区末条（即当前消息）以避免与直连 VLM 路径重复识别同一张图。
        下载与 VLM 调用均为阻塞操作，offload 到 _llm_executor 避免阻塞事件循环。
        """
        key = processed.group_id or processed.sender_id
        if not key or not self._chat_context_buffer.get(key):
            return ""
        # 末条是当前消息，直连路径已识别其图片，这里只看历史
        recent = self._chat_context_buffer[key][-window:-1]
        if not recent:
            return ""

        # 检查 VLM 是否可用
        vlm = None
        vlm_available = False
        try:
            vlm = get_vlm_llm()
            vlm_available = vlm._ensure_provider()
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        lines = []
        img_count = 0
        max_ctx_images = 2

        for msg in recent:
            line = f"[{msg['sender']}] {msg['text']}"

            # 历史消息有图片且 VLM 可用时自动识别
            if vlm_available and msg.get('images') and img_count < max_ctx_images:
                for img_url in msg['images']:
                    if img_count >= max_ctx_images:
                        break
                    local_path = await loop.run_in_executor(
                        self._llm_executor, self._download_ctx_image, img_url
                    )
                    if local_path:
                        try:
                            desc = await loop.run_in_executor(
                                self._llm_executor,
                                vlm.chat_with_image,
                                "描述这张图片的内容",
                                [local_path],
                            )
                            if desc:
                                line += f"\n  [图片: {desc[:200]}]"
                                img_count += 1
                        except Exception:
                            pass

            lines.append(line)

        return "\n".join(lines)

    async def _handle_respond_message(self, processed: ProcessedMessage, adapter_instance: str = None):
        """处理需要响应的消息

        Args:
            processed: 处理后的消息
            adapter_instance: 来源适配器实例名，用于同类多实例精确路由
        """
        # ================================================================
        # 格式化用户消息（参考 KiraAI 格式）
        # ================================================================
        # 平台
        platform_name = processed.platform.value if processed.platform else adapter_instance or "unknown"

        # 构建消息头：[At xxx] [Reply xxx] 内容
        msg_parts = []
        if processed.at_targets:
            for at_id in processed.at_targets:
                msg_parts.append(f"[At {at_id}]")
        if processed.reply_to:
            if processed.reply_text:
                msg_parts.append(f"[回复: {processed.reply_text}]")
            else:
                msg_parts.append(f"[Reply {processed.reply_to}]")
        msg_parts.append(processed.text or "")
        user_input = " ".join(msg_parts)

        # ================================================================
        # 注入时间和环境元数据
        # ================================================================
        import datetime
        now = datetime.datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")

        env_lines = [
            f"\n[当前时间] {time_str}",
            f"[消息元数据] 消息ID={processed.message_id}，发送者昵称={processed.sender_name}",
        ]
        if processed.is_group_message:
            env_lines.append(f"群ID={processed.group_id}")
            if processed.group_name:
                env_lines[-1] += f"，群名称={processed.group_name}"
            chat_type = "群聊"
        else:
            chat_type = "私聊"
        env_lines.append(f"[环境] 平台={platform_name}，聊天类型={chat_type}")

        user_input += "，" .join(env_lines)

        # 追加富媒体信息到 LLM 上下文
        extra_media = []
        if processed.voices:
            extra_media.append(f"[收到 {len(processed.voices)} 条语音消息]")
        if processed.faces:
            extra_media.append(f"[收到 {len(processed.faces)} 个QQ表情]")
        if processed.stickers:
            extra_media.append(f"[收到 {len(processed.stickers)} 个动画表情]")
        if processed.videos:
            extra_media.append(f"[收到 {len(processed.videos)} 个视频]")
        if extra_media:
            user_input += "\n" + " ".join(extra_media)

        # 维护昵称→ID 映射表（按群分组，供发送时解析 @ 用）
        if processed.sender_name and processed.sender_id:
            group_key = processed.group_id or "_private"
            if group_key not in self._name_to_id:
                self._name_to_id[group_key] = {}
            self._name_to_id[group_key][processed.sender_name] = processed.sender_id

        logger.info("处理 %s (%s): %s", processed.sender_name, processed.reason, processed.text)

        is_group = processed.group_id is not None
        target_id = processed.group_id if processed.group_id else processed.sender_id

        try:
            # 条件图片识别：有图片 + 满足触发条件时先用 VLM 识别
            if processed.images and self._should_recognize_image(processed):
                try:
                    vlm_llm = get_vlm_llm()
                    loop = asyncio.get_running_loop()
                    # VlmLLM 只吃本地路径，先把图片 URL 下载到 temp；
                    # 下载与 VLM 调用均为阻塞操作，offload 到线程池避免阻塞事件循环
                    max_vlm_images = 4  # 与 VlmLLM.MAX_IMAGES 对齐
                    local_paths = []
                    for img_url in (processed.images or [])[:max_vlm_images]:
                        p = await loop.run_in_executor(
                            self._llm_executor, self._download_ctx_image, img_url
                        )
                        if p:
                            local_paths.append(p)
                    vlm_result = None
                    if local_paths:
                        vlm_result = await loop.run_in_executor(
                            self._llm_executor,
                            vlm_llm.chat_with_image,
                            processed.text or "",
                            local_paths,
                        )
                    if vlm_result:
                        logger.info("VLM 图片识别结果: %s", vlm_result[:200])
                        user_input = f"{user_input}\n\n[图片识别结果]\n{vlm_result}"
                except Exception as e:
                    logger.warning("VLM 图片识别失败: %s", e)

            # 追加滑动上下文窗口
            if processed.text:
                ctx_window_cfg = config_loader.bot.context
                if ctx_window_cfg.chat_context_enabled and ctx_window_cfg.chat_context_window > 0:
                    ctx = await self._build_context_window(processed, ctx_window_cfg.chat_context_window)
                    if ctx:
                        logger.debug("追加上下文窗口 (%d 条)", ctx_window_cfg.chat_context_window)
                        user_input = f"以下是最近的聊天记录：\n{ctx}\n\n---\n{user_input}"

            chatllm_reply = await self._call_chatllm(user_input)
            parsed = parse_xml_msg(chatllm_reply)

            # AI 使用 <msg></msg> 主动结束对话，不发送任何消息
            if parsed.get("skip_reply") and not parsed.get("messages") and not self._has_tool_content(parsed):
                logger.info("AI 选择不回复消息 (skip_reply) -> %s", target_id)
                return

            if parsed.get("parse_error"):
                logger.warning("XML 解析失败，使用原始回复")
                await self._send_reply(
                    adapter_instance or processed.platform.value,
                    target_id,
                    chatllm_reply,
                    reply_to=processed.message_id,
                    is_group=is_group
                )
                return

            first_messages = parsed.get("messages", [])
            needs_follow_up = self._has_tool_content(parsed) or parse_function_call(chatllm_reply) is not None

            # ChatLLM 可能返回不包含 <msg> XML 标签的文本（如纯文本回复）
            # 此时 parse_xml_msg 返回空消息列表但不报错，导致回复被静默丢弃
            if not first_messages and not needs_follow_up:
                logger.warning("ChatLLM 返回了非 XML 格式回复，直接作为纯文本发送")
                await self._send_reply(
                    adapter_instance or processed.platform.value,
                    target_id,
                    chatllm_reply,
                    reply_to=processed.message_id,
                    is_group=is_group
                )
                return

            if needs_follow_up:
                # 多轮对话：先发送首条回复
                await self._send_message_batch(
                    processed, first_messages[:MAX_SPLIT_COUNT], adapter_instance=adapter_instance
                )
                # 执行后续操作并获取最终回复
                final_messages = await self._resolve_follow_up(chatllm_reply, parsed)
                await self._send_message_batch(
                    processed, final_messages[:MAX_SPLIT_COUNT], adapter_instance=adapter_instance
                )
            else:
                # 普通回复直接发送
                await self._send_message_batch(
                    processed, first_messages[:MAX_SPLIT_COUNT], adapter_instance=adapter_instance
                )

        except Exception as e:
            logger.error("处理消息时出错: %s", e, exc_info=True)
            # 给用户回显错误提示
            error_msg = f"[系统] 处理消息时出了点状况：{e}"
            await self._send_reply(
                adapter_instance or processed.platform.value,
                target_id,
                error_msg,
                reply_to=processed.message_id,
                is_group=is_group
            )

    async def _send_message_batch(self, processed: ProcessedMessage, messages: list, adapter_instance: str = None):
        """批量发送消息，每条消息前模拟打字延迟（包括第一条），句间额外停顿"""
        is_group = processed.group_id is not None
        target_id = processed.group_id if processed.group_id else processed.sender_id
        inter_delay = getattr(config_loader.bot.bot, 'typing_inter_delay', 2.0)
        for idx, msg in enumerate(messages):
            reply_text = self._extract_message_text(msg)
            if reply_text or msg.images:
                # 打字延迟：每条消息发送前等待，模拟真人逐条打字
                # 纯图片消息（reply_text 为空）给一个基础延迟，避免瞬发像机器人
                text_len = len(reply_text) if reply_text else 20
                await asyncio.sleep(calculate_split_interval(text_len))
                # AI 可主动通过 <at_targets> 指定 @ 谁（用昵称）；不写就不 @
                raw_at = msg.at_targets or []
                at_targets = None
                if raw_at:
                    at_list = []
                    group_key = processed.group_id or "_private"
                    name_map = self._name_to_id.get(group_key, {})
                    for name in raw_at:
                        qq_id = "all" if name == "all" else name_map.get(name)
                        if qq_id:
                            at_list.append(qq_id)
                    if at_list:
                        at_targets = at_list
                # AI 可主动通过 <reply> 指定引用回复的消息 ID；
                # 不写 <reply> 则不引用（而非默认引用当前消息）
                reply_to = msg.reply_to or None
                await self._send_reply(
                    adapter_instance or processed.platform.value,
                    target_id,
                    reply_text,
                    reply_to=reply_to,
                    is_group=is_group,
                    at_targets=at_targets,
                    images=msg.images or None,
                )
                # 句与句之间的额外停顿（最后一条不等待）
                if idx < len(messages) - 1:
                    await asyncio.sleep(inter_delay)

    @staticmethod
    def _has_tool_content(parsed: dict, raw_reply: str = "") -> bool:
        """检查解析结果中是否还有待处理的工具/动作/计划/FC 内容"""
        if parsed.get("actions") or parsed.get("tool") or parsed.get("plan"):
            return True
        if raw_reply and parse_function_call(raw_reply) is not None:
            return True
        return False

    async def _call_chatllm_with_timeout(self, user_input: str, timeout: float) -> str:
        """带超时的 ChatLLM 调用

        Args:
            user_input: 用户输入
            timeout: 超时秒数

        Returns:
            AI 回复文本，超时时返回错误提示
        """
        if not user_input:
            return ""
        try:
            return await asyncio.wait_for(
                self._call_chatllm(user_input),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning("AgentExecutor 步骤超时 (%.1fs)", timeout)
            timeout_msg = "[系统] 思考时间较长，已自动结束当前推理。"
            return f"<msg><text>{timeout_msg}</text></msg>"

    async def _resolve_follow_up(self, chatllm_reply: str, parsed: Optional[dict] = None) -> list:
        """
        AgentExecutor 多步骤推理循环。

        每轮执行当前回复中所有待处理的工具/动作/计划/FC，
        将结果汇总回送 ChatLLM，重复直到达到最大轮数或没有更多工具内容。
        """
        if parsed is None:
            parsed = parse_xml_msg(chatllm_reply)

        bot_config = config_loader.bot.bot
        max_steps = bot_config.max_agent_steps
        per_step_timeout = bot_config.per_step_timeout
        current_reply = chatllm_reply
        current_parsed = parsed
        iteration = 0
        # 用于去重 bus 事件发射（按事件名+数据字符串）
        _event_seen: set = set()

        def _emit_once(name: str, data, subscriber: str = "user") -> None:
            key = (name, str(data))
            if key not in _event_seen:
                _event_seen.add(key)
                bus.emit(name, data, subscriber)

        while iteration < max_steps:
            iteration += 1
            logger.debug("AgentExecutor 第 %d/%d 轮", iteration, max_steps)
            remaining = max_steps - iteration

            # ── 批量收集本轮所有可执行操作 ──
            result_parts = []  # [(title, content), ...]

            # Phase A: 内嵌 Function Calling
            has_func, func_result = handle_function_call(current_reply)
            if has_func:
                logger.info("[Agent %d/%d] 内嵌 FC", iteration, max_steps)
                result_parts.append(("工具执行结果", str(func_result)))
                # 统一 tool_executed 事件载荷为列表，与 Phase B 保持一致
                _emit_once("tool_executed", [func_result] if not isinstance(func_result, list) else func_result)

            # Phase B: <act> 标签
            if current_parsed.get("actions"):
                logger.info("[Agent %d/%d] 执行动作: %s",
                            iteration, max_steps, current_parsed["actions"])
                results = await self._execute_actions(current_parsed["actions"])
                if results:
                    texts = []
                    for i, r in enumerate(results, 1):
                        texts.append(f"[{i}] {r}")
                    result_parts.append((
                        "动作执行结果",
                        f"共执行 {len(results)} 个工具：\n" + "\n".join(texts)
                    ))
                    _emit_once("tool_executed", results)
                else:
                    result_parts.append(("动作执行失败", "所有工具执行均失败，请告知用户。"))

            # Phase C: <tool> 标签
            if current_parsed.get("tool"):
                logger.info("[Agent %d/%d] 查询工具列表", iteration, max_steps)
                tools_result = self.toolllm.query_tools()
                first_reply = self._extract_reply_text(current_parsed)
                tool_content = (
                    f'你刚才对用户说："{first_reply}"\n\n'
                    f"现在我已经获取到可用工具列表：\n{tools_result}\n\n"
                    f"请介绍这些工具的功能。"
                )
                result_parts.append(("可用工具列表", tool_content))
                _emit_once("tools_queried", tools_result)

            # Phase D: <plan> 标签
            if current_parsed.get("plan"):
                logger.info("[Agent %d/%d] 制定计划", iteration, max_steps)
                plan_result = await get_planllm().generate_async(current_parsed["plan"])
                first_reply = self._extract_reply_text(current_parsed)
                plan_content = (
                    f'你刚才对用户说："{first_reply}"\n\n'
                    f"现在我已经获取到日程信息：\n{plan_result}\n\n"
                    "请整合以上信息，给用户一个完整的回复。"
                    "如果日程为空，可以说'今天还没有安排呢，要不要添加一些？'"
                    "如果有安排，请列出具体事项。"
                )
                result_parts.append(("日程信息", plan_content))
                _emit_once("plan_generated", plan_result)

            # ── 本轮无任何操作 → 退出循环 ──
            if not result_parts:
                break

            # ── 合并结果 ──
            if len(result_parts) == 1:
                combined_result = result_parts[0][1]
            else:
                combined_result = "\n\n---\n\n".join(
                    f"【{title}】\n{content}" for title, content in result_parts
                )

            follow_up_prompt = self._build_agent_prompt(
                iteration, max_steps, combined_result,
                f"第 {iteration} 轮执行结果", remaining,
            )
            current_reply = await self._call_chatllm_with_timeout(follow_up_prompt, per_step_timeout)
            current_parsed = parse_xml_msg(current_reply)

        if iteration >= max_steps and self._has_tool_content(current_parsed, current_reply):
            logger.warning(
                "AgentExecutor 已达最大轮数 (%d)，仍有未处理的工具调用，"
                "最终回复可能不完整", max_steps
            )

        return current_parsed.get("messages", [])

    def _build_agent_prompt(self, iteration: int, max_steps: int,
                            result: str, title: str, remaining: int) -> str:
        """构建带步数感知的 Agent 提示词

        Args:
            iteration: 当前轮次
            max_steps: 最大轮数
            result: 工具/动作执行结果
            title: 结果标题
            remaining: 剩余可用轮数

        Returns:
            格式化后的提示词
        """
        if remaining > 0:
            return (
                f"[Agent 第 {iteration}/{max_steps} 轮] {title}：\n"
                f"{result}\n\n"
                f"这是第 {iteration} 次工具调用（最多允许 {max_steps} 次推理步骤）。"
                f"你还有 {remaining} 次机会。\n"
                f"如果任务已完成，请直接回复用户；如果还需要查询更多信息、执行更多操作，\n"
                f"可以继续使用 <act>/<tool>/<plan> 标签。"
            )
        else:
            return (
                f"[Agent 第 {iteration}/{max_steps} 轮 — 最后一轮] {title}：\n"
                f"{result}\n\n"
                f"这是最后一轮推理。请根据已有信息给用户一个完整回复，"
                f"不要再使用 <act>/<tool>/<plan> 标签。"
            )

    async def _execute_actions(self, actions: list) -> list:
        """执行动作列表，返回所有执行结果"""
        results = []
        loop = asyncio.get_running_loop()
        for i, action in enumerate(actions, 1):
            logger.info("ToolLLM 处理动作 %d/%d: %s", i, len(actions), action)
            try:
                fc_output = await loop.run_in_executor(
                    self._llm_executor, self.toolllm.generate_fc, action
                )
                logger.debug("ToolLLM 输出: %s", fc_output)
            except Exception as e:
                logger.error("ToolLLM generate_fc 失败: %s", e)
                continue

            func_call = parse_function_call(fc_output)
            if func_call:
                logger.info("执行工具: %s", func_call["name"])
                tool_result = await loop.run_in_executor(
                    self._llm_executor,
                    execute_function, func_call["name"], func_call["parameters"]
                )
                logger.info("执行结果: %s", tool_result)
                results.append(tool_result)
            else:
                logger.warning("无法解析 Function Calling")
        return results

    def _should_recognize_image(self, processed) -> bool:
        """判断是否应触发图片识别。
        条件：@提及 / 引用回复 / 纯贴图(有图无文字) / 唤醒关键词
        """
        if getattr(processed, "at_targets", None):
            return True
        if getattr(processed, "reply_to", None):
            return True
        text = getattr(processed, "text", "") or ""
        images = getattr(processed, "images", []) or []
        if not text.strip() and images:
            return True
        wake_keywords = config_loader.bot.wake.waking_keywords
        if wake_keywords and text:
            text_lower = text.lower()
            for kw in wake_keywords:
                if kw.lower() in text_lower:
                    return True
        return False

    async def _call_chatllm(self, user_input: str) -> str:
        """调用 ChatLLM 生成回复（非阻塞，使用线程池执行同步 API 调用）

        Args:
            user_input: 用户输入

        Returns:
            AI 回复文本
        """
        if not user_input:
            return ""

        if self.chat is None:
            logger.error("ChatLLM 未初始化")
            return "[系统错误] ChatLLM 未初始化，请检查 services.yaml 配置"

        # 创建停止事件和线程
        stop_event = threading.Event()
        spinner_thread = threading.Thread(
            target=spinning_think, args=(stop_event,), daemon=True
        )
        spinner_thread.start()

        try:
            # 在专用线程池中执行同步 API 调用，避免阻塞事件循环
            loop = asyncio.get_running_loop()
            chatllm_reply = await loop.run_in_executor(
                self._llm_executor, self.chat.chat, user_input
            )
        finally:
            # 停止动画（daemon 线程无需 join，进程退出时自动终止）
            stop_event.set()

        return chatllm_reply

    async def _generate_reply(self, user_input: str) -> list:
        """生成 AI 回复（控制台模式入口）

        Args:
            user_input: 用户输入

        Returns:
            消息对象列表
        """
        if not user_input:
            return []

        chatllm_reply = await self._call_chatllm(user_input)
        return await self._resolve_follow_up(chatllm_reply)

    def _extract_reply_text(self, parsed: dict) -> str:
        """从解析结果中提取回复文本（兼容旧版，合并所有消息）

        Args:
            parsed: 解析后的消息

        Returns:
            回复文本
        """
        texts = []
        if parsed["messages"]:
            for msg in parsed["messages"]:
                for elem in msg.elements:
                    texts.append(elem.content)
        return " ".join(texts)

    def _extract_message_text(self, message) -> str:
        """从单个 Message 对象中提取文本

        Args:
            message: Message 对象

        Returns:
            消息文本
        """
        return format_message_for_display(message)

    async def _send_reply(
        self,
        platform: str,
        target_id: str,
        reply: str,
        reply_to: Optional[str] = None,
        is_group: bool = False,
        at_targets: Optional[list] = None,
        images: Optional[list] = None,
    ):
        """发送回复消息

        Args:
            platform: 平台名称
            target_id: 目标 ID
            reply: 回复内容
            reply_to: 回复的消息 ID（可选）
            is_group: 是否为群消息
            at_targets: @目标列表（群聊时传入发送者ID以触发真实提醒）
            images: 图片 URL/路径列表（可选）
        """
        if not self.adapter_bridge or (not reply and not images):
            return

        try:
            success = await self.adapter_bridge.send_message(
                adapter_id=platform,
                target_id=target_id,
                text=reply,
                images=images,
                reply_to=reply_to,
                is_group=is_group,
                at_targets=at_targets,
            )
            if success:
                logger.info("发送成功 [%s] -> %s", platform, target_id)
            else:
                logger.warning("发送失败 [%s] -> %s", platform, target_id)
        except Exception as e:
            logger.error("发送错误: %s", e)

    async def start_adapters(self):
        """启动所有配置的适配器"""
        if not self.adapter_bridge:
            logger.error("适配器桥接器未初始化")
            return

        logger.info("启动适配器...")
        await self.adapter_bridge.start_pending_adapters()

        running_adapters = self.adapter_bridge.get_manager().list_running_adapters()
        if running_adapters:
            logger.info("运行中的适配器: %s", ", ".join(running_adapters))

            # 绑定 QQ API 客户端并注册群成员查询工具
            self._init_qq_api_tool()
        else:
            logger.info("没有运行中的适配器（将进入控制台模式）")

    def _init_qq_api_tool(self):
        """绑定 QQ 适配器为 API 客户端，注册群成员查询工具"""
        try:
            mgr = self.adapter_bridge.get_manager()
            qq_inst = mgr.resolve_adapter_id("qq")
            if not qq_inst:
                logger.info("[QQApi] 未找到 QQ 适配器实例，跳过")
                return

            adapter = mgr._adapters.get(qq_inst)
            if not adapter:
                return

            from .adapter.src.qq.adapter import QQApiClient
            QQApiClient.bind(adapter)

            # 用插件注册机制把 query_group_members 动态注册进 function_caller
            # _plugin_dispatch 是同步契约，内部用 run_coroutine_threadsafe 桥接 async 调用
            _loop = asyncio.get_running_loop()

            def _run_query(parameters):
                group_id = parameters.get("group_id", "")
                if not group_id:
                    return {"status": "failed", "error": "缺少 group_id 参数"}
                future = asyncio.run_coroutine_threadsafe(
                    QQApiClient.get_group_member_list(group_id), _loop
                )
                try:
                    members = future.result(timeout=30)
                except Exception as e:
                    return {"status": "failed", "error": f"查询群成员失败: {e}"}
                # 填充 _name_to_id（群成员映射，按群分组）
                group_key = group_id
                if group_key not in self._name_to_id:
                    self._name_to_id[group_key] = {}
                for m in members:
                    uid = m.get("user_id", "")
                    nick = m.get("nickname", "")
                    if uid and nick:
                        self._name_to_id[group_key][nick] = uid
                if not members:
                    return {"status": "ok", "members": [], "message": "该群没有成员或查询失败"}
                return {
                    "status": "ok",
                    "members": members,
                    "message": f"查询到 {len(members)} 名群成员",
                }

            from .function_caller import register_plugin_handler
            register_plugin_handler("query_group_members", _run_query)

            # 注册撤回消息工具
            def _run_delete_msg(parameters):
                msg_id = parameters.get("message_id", "")
                if not msg_id:
                    return {"status": "failed", "error": "缺少 message_id 参数"}
                future = asyncio.run_coroutine_threadsafe(
                    QQApiClient.delete_msg(msg_id), _loop
                )
                try:
                    ok = future.result(timeout=10)
                except Exception as e:
                    return {"status": "failed", "error": f"撤回消息失败: {e}"}
                if not ok:
                    return {"status": "failed", "error": "撤回失败"}
                return {"status": "ok", "message": f"消息 {msg_id} 已撤回"}

            register_plugin_handler("delete_msg", _run_delete_msg)

            from .tools.registry import get_registry, ToolDefinition, ToolParameter
            get_registry().register(
                ToolDefinition(
                    name="query_group_members",
                    description="获取群成员列表，查询群里用户的昵称和 QQ 号",
                    parameters=[
                        ToolParameter("group_id", "群 ID，如 12345678"),
                    ],
                )
            )
            get_registry().register(
                ToolDefinition(
                    name="delete_msg",
                    description="撤回指定消息，需要提供消息 ID。只能撤回机器人自己发送的消息。",
                    parameters=[
                        ToolParameter("message_id", "要撤回的消息 ID"),
                    ],
                )
            )

            # 刷新 ToolLLM 的工具定义列表（必须在所有工具注册之后）
            if self.toolllm is not None:
                self.toolllm.rebuild_tool_definitions()

            logger.info("[QQApi] 群成员查询、撤回消息工具已注册")
        except Exception as e:
            logger.warning("[QQApi] 初始化失败（不影响核心运行）: %s", e)

    async def stop_adapters(self):
        """停止所有适配器"""
        if self.adapter_bridge:
            logger.info("停止适配器...")
            await self.adapter_bridge.stop_all()

    async def run_console_mode(self):
        """运行控制台交互模式"""
        print("\n========================================")
        print("  Tale AI  - 控制台模式")
        print("========================================\n")
        print("开始对话：")
        print("- 输入 'quit' 退出")
        print("- 输入 'clear' 清空历史")
        print("- 按 Ctrl+C 中断\n")

        try:
            while self._running:
                try:
                    user_input = input("你: ").strip()
                except KeyboardInterrupt:
                    print("\n对话结束")
                    break

                if user_input.lower() == 'quit':
                    print("对话结束")
                    break

                if user_input.lower() == 'clear':
                    self.chat.clear_history()
                    print("历史已清空\n")
                    continue

                if not user_input:
                    continue

                # 生成回复
                messages = await self._generate_reply(user_input)
                if messages:
                    for msg in messages:
                        reply_text = self._extract_message_text(msg)
                        if reply_text:
                            print(f"AI: {reply_text}\n")

        except KeyboardInterrupt:
            print("\n\n对话被中断")

    async def run(self):
        """统一运行：初始化 → 等待用户/WebUI 控制"""
        self._running = True
        self._shutdown_event = asyncio.Event()

        self.initialize()

        # 自动启动配置中的适配器
        await self.start_adapters()

        # 确保今日计划已自动生成
        try:
            from .llm import get_planllm
            get_planllm().ensure_today_plan()
        except Exception as e:
            logger.warning("自动生成今日计划失败（不影响核心运行）: %s", e)

        print("\n========================================")
        print("  Tale AI 已启动")
        print("  适配器请通过 WebUI 管理")
        print("  具体面板请访问 http://127.0.0.1:32456")
        print("========================================\n")
        print("按 Ctrl+C 停止\n")

        try:
            await self._shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("收到停止信号")

        # 停止所有适配器（确保 asyncio 任务正确清理）
        logger.info("正在停止适配器...")
        await self.stop_adapters()

        print("再见！")

    def shutdown(self):
        """关闭应用"""
        self._running = False
        if self._shutdown_event:
            self._shutdown_event.set()


# 全局实例
core_instance: Optional[TaleCore] = None
# 主事件循环引用（供 WebUI 线程提交异步任务用）
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None


def get_core() -> TaleCore:
    """获取全局核心实例（惰性初始化）"""
    global core_instance
    if core_instance is None:
        core_instance = TaleCore()
        core_instance.initialize()
    return core_instance


def get_main_event_loop() -> Optional[asyncio.AbstractEventLoop]:
    """获取主事件循环（供 WebUI 等子线程使用）"""
    return _main_event_loop


def main():
    """主入口函数"""
    # 首次启动时确保 data/ 目录和默认配置就绪
    from .data_initializer import initialize_data
    initialize_data()

    # 设置日志
    from core.utils.logger import setup_logging
    setup_logging(level=__import__('logging').INFO)

    # 设置信号处理
    def signal_handler(sig, frame):
        logger.info("收到中断信号，正在关闭...")
        if core_instance:
            core_instance.shutdown()

    signal.signal(signal.SIGINT, signal_handler)

    # 运行异步主程序
    core = get_core()
    try:
        global _main_event_loop
        _main_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_main_event_loop)
        _main_event_loop.run_until_complete(core.run())
    except Exception as e:
        logger.error("程序运行出错: %s", e, exc_info=True)
if __name__ == "__main__":
    main()
