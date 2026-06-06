import sys
import time
import threading
import asyncio
import signal
from pathlib import Path
from typing import Optional, Callable, Any, List

from .spin_think import spinning_think
from .bus import NextBus, bus
from .llm import ChatLLM, get_planllm, ToolLLM
from .config import CHAT_API_KEY, CHAT_MODEL, CHAT_URL
from .config import PLAN_API_KEY, PLAN_MODEL, PLAN_URL
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
    bot = provide.config_loader.bot.bot
    speed_ms = getattr(bot, 'typing_speed', 50.0)
    min_delay = getattr(bot, 'typing_min_delay', 0.5)
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

    def initialize(self):
        """初始化核心组件（幂等，可多次调用）"""
        if self.chat is not None:
            return
        # 初始化 LLM
        self.chat = ChatLLM(
            api_key=CHAT_API_KEY,
            model=CHAT_MODEL,
            url=CHAT_URL
        )
        self.toolllm = ToolLLM(
            api_key=PLAN_API_KEY,
            model=PLAN_MODEL,
            url=PLAN_URL
        )

        # 初始化消息处理器（从配置加载）
        self._init_message_processor()

        # 初始化适配器桥接器
        self.adapter_bridge = AdapterEventBridge(bus, config_loader)
        self.adapter_bridge.initialize()

        # 注册事件处理器
        self._register_event_handlers()

        # 注册 wechat_moments 专属处理器
        bus.on("wechat_moments_message", self._handle_wechat_moments_message)

        # 初始化插件管理器
        self._init_plugin_manager()

        logger.info("核心组件初始化完成")

    def _init_message_processor(self):
        """初始化消息处理器"""
        # 从配置构建处理器配置
        qq_config = config_loader.adapters.qq
        if qq_config.enabled:
            processor_config = PlatformConfigBuilder.from_qq_config(qq_config)
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

    def _init_plugin_manager(self):
        """初始化插件管理器"""
        try:
            from .plugin import PluginManager

            project_root = Path(__file__).parent.parent
            plugins_config = getattr(config_loader, "_plugins_config", {})

            self.plugin_manager = PluginManager(
                plugins_dir=project_root / "plugins",
                config=plugins_config,
            )
            self.plugin_manager.load_all_enabled()

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

    async def _handle_respond_message(self, processed: ProcessedMessage, adapter_instance: str = None):
        """处理需要响应的消息

        Args:
            processed: 处理后的消息
            adapter_instance: 来源适配器实例名，用于同类多实例精确路由
        """
        # 构建用户输入
        if processed.is_group_message:
            user_input = f"[{processed.sender_name}] {processed.text}"
        else:
            user_input = processed.text or ""

        logger.info("处理 %s (%s): %s", processed.sender_name, processed.reason, processed.text)

        is_group = processed.group_id is not None
        target_id = processed.group_id if processed.group_id else processed.sender_id

        try:
            chatllm_reply = await self._call_chatllm(user_input)
            parsed = parse_xml_msg(chatllm_reply)

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
            needs_follow_up = parsed.get("tool") or parsed.get("plan") or parsed.get("actions")

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
        """批量发送消息，每条消息前模拟打字延迟（包括第一条）"""
        is_group = processed.group_id is not None
        target_id = processed.group_id if processed.group_id else processed.sender_id
        for msg in messages:
            reply_text = self._extract_message_text(msg)
            if reply_text:
                # 打字延迟：每条消息发送前等待，模拟真人逐条打字
                await asyncio.sleep(calculate_split_interval(len(reply_text)))
                await self._send_reply(
                    adapter_instance or processed.platform.value,
                    target_id,
                    reply_text,
                    reply_to=processed.message_id,
                    is_group=is_group
                )

    async def _resolve_follow_up(self, chatllm_reply: str, parsed: dict = None) -> list:
        """
        解析首次 AI 回复，执行需要的工具/计划/动作，返回最终消息列表。
        统一处理 <tool>, <plan>, <act> 以及内嵌 Function Calling 的多轮逻辑。
        """
        if parsed is None:
            parsed = parse_xml_msg(chatllm_reply)

        # 1. 内嵌 Function Calling（直接在 JSON 中）
        has_func, func_result = handle_function_call(chatllm_reply)
        if has_func:
            logger.info("工具执行结果: %s", func_result)
            follow_up = f"工具执行结果：\n{func_result}\n\n请根据以上结果，给用户一个友好的回复。"
            reply = await self._call_chatllm(follow_up)
            parsed_2 = parse_xml_msg(reply)
            bus.emit("tool_executed", func_result, "user")
            return parsed_2.get("messages", [])

        # 2. <tool> 标签
        if parsed.get("tool"):
            logger.info("ToolLLM 查询工具列表: %s", parsed["tool"])
            tools_result = self.toolllm.query_tools()
            first_reply = self._extract_reply_text(parsed)
            follow_up = f"""你刚才对用户说："{first_reply}"

现在我已经获取到可用工具列表：
{tools_result}

请给用户一个完整的回复，介绍这些工具的功能。"""
            reply = await self._call_chatllm(follow_up)
            parsed_2 = parse_xml_msg(reply)
            bus.emit("tools_queried", tools_result, "user")
            return parsed_2.get("messages", [])

        # 3. <act> 标签
        if parsed.get("actions"):
            results = await self._execute_actions(parsed["actions"])
            if results:
                follow_up = f"工具执行结果（共{len(results)}个）：\n"
                for i, result in enumerate(results, 1):
                    follow_up += f"\n[{i}] {result}\n"
                follow_up += "\n请根据以上结果，给用户一个友好的回复。"
                reply = await self._call_chatllm(follow_up)
                parsed_2 = parse_xml_msg(reply)
                bus.emit("tool_executed", results, "user")
                return parsed_2.get("messages", [])
            return parsed.get("messages", [])

        # 4. <plan> 标签
        if parsed.get("plan"):
            logger.info("PlanLLM 制定计划: %s", parsed["plan"])
            plan_result = await get_planllm().generate_async(parsed["plan"])
            first_reply = self._extract_reply_text(parsed)
            follow_up = f"""你刚才对用户说："{first_reply}"

现在我已经获取到日程信息：
{plan_result}

请整合以上信息，给用户一个完整的回复。如果日程为空，可以说"今天还没有安排呢，要不要添加一些？"如果有安排，请列出具体事项。"""
            reply = await self._call_chatllm(follow_up)
            parsed_2 = parse_xml_msg(reply)
            bus.emit("plan_generated", plan_result, "user")
            return parsed_2.get("messages", [])

        return parsed.get("messages", [])

    async def _execute_actions(self, actions: list) -> list:
        """执行动作列表，返回所有执行结果"""
        results = []
        for i, action in enumerate(actions, 1):
            logger.info("ToolLLM 处理动作 %d/%d: %s", i, len(actions), action)
            try:
                fc_output = await asyncio.to_thread(self.toolllm.generate_fc, action)
                logger.debug("ToolLLM 输出: %s", fc_output)
            except Exception as e:
                logger.error("ToolLLM generate_fc 失败: %s", e)
                continue

            func_call = parse_function_call(fc_output)
            if func_call:
                logger.info("执行工具: %s", func_call["name"])
                tool_result = execute_function(func_call["name"], func_call["parameters"])
                logger.info("执行结果: %s", tool_result)
                results.append(tool_result)
            else:
                logger.warning("无法解析 Function Calling")
        return results

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
        spinner_thread = threading.Thread(target=spinning_think, args=(stop_event,))
        spinner_thread.start()

        try:
            # 在线程池中执行同步 API 调用，避免阻塞事件循环
            chatllm_reply = await asyncio.to_thread(self.chat.chat, user_input)
        finally:
            # 停止动画并等待线程结束
            stop_event.set()
            spinner_thread.join()

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
        is_group: bool = False
    ):
        """发送回复消息

        Args:
            platform: 平台名称
            target_id: 目标 ID
            reply: 回复内容
            reply_to: 回复的消息 ID（可选）
            is_group: 是否为群消息
        """
        if not self.adapter_bridge or not reply:
            return

        try:
            success = await self.adapter_bridge.send_message(
                adapter_id=platform,
                target_id=target_id,
                text=reply,
                reply_to=reply_to,
                is_group=is_group
            )
            if success:
                logger.info("发送成功 -> %s", target_id)
            else:
                logger.warning("发送失败 -> %s", target_id)
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
        else:
            logger.info("没有运行中的适配器（将进入控制台模式）")

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
