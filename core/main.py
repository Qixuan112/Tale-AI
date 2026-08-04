import sys
import time
import threading
import asyncio
import signal
import functools
from pathlib import Path
from typing import Optional, Callable, Any, List, Dict

from .spin_think import spinning_think
from .bus import NextBus, bus
from .llm import ChatLLM, get_planllm, ToolLLM, get_vlm_llm
from .llm.provider import OpenAICompatibleProvider, provider_manager
from .utils.cache import BoundedCache
from .utils.id_sanitizer import IDSanitizer
from .config.provide import (
    get_chat_api_key, get_chat_model, get_chat_url,
    get_plan_api_key, get_plan_model, get_plan_url,
    get_tool_api_key, get_tool_model, get_tool_url,
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
from .chat import SessionManager
from .bridge import BridgeState
from .utils import get_logger
from .utils.cache import BoundedCache

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


class ChatLLMAdapter:
    """把 ChatLLM 适配为 ChatAgent 需要的 provider 接口（#183 集成）

    ChatAgent 调用 `provider.chat(messages)` 传入完整消息列表，
    此处转发给 ChatLLM.chat()：其无状态模式会注入 dynamic reminder
    （当前时间/今日日程）、执行 RAG 检索与上下文裁剪，保证提示词
    行为与旧路径完全一致。返回 None 时表示上游 API 失败。
    """

    def __init__(self, chatllm):
        self._chatllm = chatllm

    @property
    def chatllm(self):
        return self._chatllm

    def _prepend_system_head(self, messages: list) -> list:
        """把 ChatLLM 的 system 头（角色人格/对话示例等）拼到消息列表最前。

        旧路径（有状态）在 set_session()/refresh_context() 时把
        ``context.build_messages_head(cache_strategy)`` 写入 self.messages，
        ChatLLM.chat() 使用实例状态时该头自然在列表中；而无状态路径
        （messages=history 参数）只对传入列表追加/裁剪，从不注入 system 头，
        导致 AI 丢失人格设定且破坏前缀缓存命中。此处显式补齐，
        保证与旧路径行为一致（P1）。
        """
        head = self._chatllm.context.build_messages_head(self._chatllm.cache_strategy)
        return list(head) + list(messages)

    def chat(self, messages):
        """同步 chat 接口（ChatAgent 内部按 sync provider 处理）

        最后一条消息作为当前用户输入，其余作为历史传入 ChatLLM 的无状态模式
        （messages=history 参数），由 ChatLLM 内部注入 dynamic reminder
        （当前时间/今日日程）、执行 RAG 检索与上下文裁剪，保证提示词
        行为与旧路径一致。system 头由本适配器显式补齐（见
        _prepend_system_head，修复 ChatAgent 路径丢失人格设定的问题）。
        """
        try:
            if not messages:
                return None
            user_input = messages[-1].get("content", "")
            history = self._prepend_system_head(messages[:-1])
            return self._chatllm.chat(
                user_input,
                persist_content=None,
                save_to_session=False,
                sid=None,
                messages=history,
            )
        except Exception as e:
            logger.error("ChatLLMAdapter 调用失败: %s", e)
            return None


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
        # 无状态 ChatAgent（#183）：generate(messages, session_id, timeout)，
        # 内部自带 per-session lock + Semaphore 并发控制。
        # 兼容模式：chat_agent 为 None 时走旧 self.chat.chat() 路径。
        self.chat_agent: Optional[Any] = None
        # ChatAgent 模式的 per-session 消息快照（sid -> 消息列表）：
        # 历史由 SessionManager 统一管理，快照缓存本轮会话追加段，
        # 供 Agent 多轮循环上下文连续与最终回复落库，避免跨会话共享状态串味。
        self._chat_snapshots: Dict[str, List[Dict]] = {}
        self.toolllm: Optional[ToolLLM] = None
        self.adapter_bridge: Optional[AdapterEventBridge] = None
        self.message_processor: Optional[MessageProcessor] = None
        self.plugin_manager: Optional[Any] = None
        self._running = False
        self._shutdown_event: Optional[asyncio.Event] = None
        self._llm_executor = None
        # ChatAgent 路径内部阻塞调用（_build_context_window 的图片下载/VLM
        # 识别）专用 executor：避免与同步 ChatLLM 兼容路径共享默认线程池，
        # 锁内串行提交的阻塞任务不会因默认池线程被占满而互相排队
        self._chat_agent_executor = None
        self._chat_context_buffer = BoundedCache(maxsize=200, ttl=7200)
        self._name_to_id = BoundedCache(maxsize=200, ttl=86400)
        self.session_manager: Optional[SessionManager] = None
        self.bridge: Optional[BridgeState] = None
        self._id_sanitizer = IDSanitizer()  # ID脱敏器
        # per-session 锁：每个会话独立锁，防止同会话消息乱序
        self._session_locks = BoundedCache(maxsize=500, ttl=7200)
        self._session_locks_lock = asyncio.Lock()  # 保护 _session_locks 访问
        # Semaphore 限流：最大并发LLM调用数（默认3，initialize时从配置更新）
        self._session_semaphore = asyncio.Semaphore(3)
        # 缓存 ChatLLM 是否支持无状态调用（在 initialize 中检测）
        self._chatllm_supports_stateless: bool = False
        # ContextBuilder 用于构建 LLM 上下文（供 Pipeline 使用）
        self.context_builder: Optional[Any] = None

    def initialize(self):
        """初始化核心组件（幂等，可多次调用）"""
        if self.chat is not None:
            return

        import concurrent.futures
        self._llm_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=8, thread_name_prefix="llm"
        )
        self._chat_agent_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="chat-agent-ctx"
        )

        # 初始化会话管理器（持久化到 data/sessions/）
        persistence = config_loader.bot.bot.persistence_enabled
        if persistence:
            self.session_manager = SessionManager(
                data_dir=str(Path(__file__).parent.parent / "data" / "sessions")
            )
            # 启动时清理过期会话（7天以上）
            self.session_manager.cleanup_expired(days=7)

        # 注册内置工具handlers（必须在 ToolRegistry 默认注册之后）
        self._register_builtin_handlers()

        # 初始化跨会话消息桥接
        self.bridge = BridgeState()

        self.chat = self._init_chatllm()
        self.chat_agent = self._init_chat_agent()

        # 初始化 ContextBuilder（供 ContextBuildStage 使用）
        from core.chat.context_builder import (
            ContextBuilder, MetadataBuilder,
            MediaRecognizer, HistoryProvider
        )
        metadata_builder = MetadataBuilder(id_sanitizer=self._id_sanitizer)
        media_recognizer = MediaRecognizer(
            vlm=get_vlm_llm(),
            timeout=3.0,
            executor=self._llm_executor,
            download_func=self._download_ctx_image
        )
        history_provider = HistoryProvider(session_manager=self.session_manager)
        self.context_builder = ContextBuilder(
            metadata_builder=metadata_builder,
            media_recognizer=media_recognizer,
            history_provider=history_provider
        )

        # 更新 Semaphore（从配置读取最大并发数）
        max_concurrent = getattr(config_loader.bot.bot, 'max_concurrent_llm', 3)
        self._session_semaphore = asyncio.Semaphore(max_concurrent)

        # 检测 ChatLLM 是否支持无状态调用（缓存结果）
        self._chatllm_supports_stateless = self._check_chatllm_stateless()
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

        # 初始化 Pipeline（StandardPipeline + 9 个 Stage）
        self._init_pipeline()

        logger.info("核心组件初始化完成")

    def _register_builtin_handlers(self):
        """注册内置工具的handlers到统一注册表"""
        from .function_caller import register_handler
        from .tools import browser, weather
        from .utils.calculator import safe_calculate

        # browser_open handler
        def browser_open_handler(parameters: dict) -> dict:
            url = parameters.get("url", "")
            if url:
                return browser.fetch_and_parse(url)
            return {"status": "failed", "error": "缺少 url 参数"}

        # browser_search handler
        def browser_search_handler(parameters: dict) -> dict:
            query = parameters.get("query", "")
            engine = parameters.get("engine", "duckduckgo")
            if query:
                return browser.browser_search(query, engine)
            return {"status": "failed", "error": "缺少 query 参数"}

        # weather_query handler
        def weather_query_handler(parameters: dict) -> dict:
            city = parameters.get("city", "")
            if city:
                return weather.query(city)
            return {"status": "failed", "error": "缺少 city 参数"}

        # calculator handler
        def calculator_handler(parameters: dict) -> dict:
            expression = parameters.get("expression", "")
            if expression:
                return safe_calculate(expression)
            return {"status": "failed", "error": "缺少 expression 参数"}

        # generate_image handler
        def generate_image_handler(parameters: dict) -> dict:
            from .llm.image_gen import get_image_generator
            prompt = parameters.get("prompt", "")
            size = parameters.get("size", "1024x1024") or "1024x1024"
            if not prompt:
                return {"status": "failed", "error": "缺少 prompt 参数"}
            image_url = get_image_generator().generate(prompt, size)
            if image_url:
                return {
                    "status": "success",
                    "image_url": image_url,
                    "message": f"已生成图片，URL: {image_url}。请在回复中用 <image>{image_url}</image> 把这张图发给用户。",
                }
            return {"status": "failed", "error": "图片生成失败（可能未配置 image_gen provider）"}

        # take_photo handler
        def take_photo_handler(parameters: dict) -> dict:
            from .llm.image_gen import get_image_generator
            raw = parameters.get("prompt", "")
            size = parameters.get("size", "1024x1024") or "1024x1024"
            if not raw:
                return {"status": "failed", "error": "缺少 prompt 参数"}
            enriched = f"写实摄影风格，超清照片质感，电影级光影与细节，颜色真实自然，4K画质，景深效果，{raw}"
            image_url = get_image_generator().generate(enriched, size)
            if image_url:
                return {
                    "status": "success",
                    "image_url": image_url,
                    "message": f"已拍照成功，URL: {image_url}。请在回复中用 <image>{image_url}</image> 把这张照片发给用户。",
                }
            return {"status": "failed", "error": "拍照失败（可能未配置 image_gen provider）"}

        # draw_picture handler
        def draw_picture_handler(parameters: dict) -> dict:
            from .llm.image_gen import get_image_generator
            raw = parameters.get("prompt", "")
            size = parameters.get("size", "1024x1024") or "1024x1024"
            style = parameters.get("style", "") or ""
            if not raw:
                return {"status": "failed", "error": "缺少 prompt 参数"}
            style_tag = f"{style}风格，" if style else ""
            enriched = f"插画创作，{style_tag}富有艺术感与表现力，色彩丰富协调，画面生动有故事性，{raw}"
            image_url = get_image_generator().generate(enriched, size)
            if image_url:
                return {
                    "status": "success",
                    "image_url": image_url,
                    "message": f"已画好，URL: {image_url}。请在回复中用 <image>{image_url}</image> 把这张画发给用户。",
                }
            return {"status": "failed", "error": "画画失败（可能未配置 image_gen provider）"}

        # Register all handlers
        register_handler("browser_open", browser_open_handler)
        register_handler("browser_search", browser_search_handler)
        register_handler("weather_query", weather_query_handler)
        register_handler("calculator", calculator_handler)
        register_handler("generate_image", generate_image_handler)
        register_handler("take_photo", take_photo_handler)
        register_handler("draw_picture", draw_picture_handler)

        logger.info("已注册 7 个内置工具handlers到统一注册表")

    def _init_chatllm(self):
        api_key = get_chat_api_key()
        model = get_chat_model()
        url = get_chat_url()
        if not api_key:
            logger.warning("ChatLLM 未配置 API Key，请通过 WebUI 配置服务商")
            return None
        try:
            return ChatLLM(
                api_key=api_key, model=model, url=url,
                session_manager=self.session_manager,
            )
        except Exception as e:
            logger.warning("ChatLLM 初始化失败: %s", e)
            return None

    def _init_chat_agent(self):
        """初始化无状态 ChatAgent（#183 集成）。

        ChatAgent 需要 provider 提供 `chat(messages) -> str` 接口：
        - 优先包装 ChatLLM 实例（复用其 dynamic reminder/RAG/上下文裁剪逻辑）
        - 其次回退到 provider_manager 的 main_llm 配置，保证热重载时重建可用
        """
        from .agent import ChatAgent
        if self.chat is not None:
            try:
                provider = ChatLLMAdapter(self.chat)
                return ChatAgent(provider=provider)
            except Exception as e:
                logger.warning("ChatAgent 包装 ChatLLM 失败，回退 provider 直连: %s", e)
        # 回退：直接用 provider_manager 解析出的 provider（热重载时 ChatLLM 可能尚不可用）
        try:
            provider, model = provider_manager.resolve("main_llm")
            if provider is None:
                return None
            # BaseProvider.chat(messages, model, ...) 的 model 是必填参数，
            # 而 ChatAgent 只调用 provider.chat(messages)：用 functools.partial
            # 绑定路由解析出的 model，否则回退路径会因缺参抛 TypeError。
            # （ChatLLMAdapter 主路径内部用 ChatLLM.model，不受影响。）
            if model and isinstance(provider, OpenAICompatibleProvider):
                provider.chat = functools.partial(provider.chat, model=model)
            return ChatAgent(provider=provider)
        except Exception as e:
            logger.warning("ChatAgent 初始化失败: %s", e)
            return None

    @staticmethod
    def _init_toolllm():
        api_key = get_tool_api_key()
        model = get_tool_model()
        url = get_tool_url()
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
        # ChatAgent 绑定 ChatLLM 实例，ChatLLM 重建后需同步重建 agent。
        # 注意：chat_agent._provider 是 ChatLLMAdapter（包装 self.chat），
        # 直接比较 _provider is self.chat 永远不匹配，会导致每次 config_reloaded
        # 都重建 agent、丢掉 per-session locks / semaphore 状态。
        # 正确比较：adapter 包装的 ChatLLM 实例（ChatLLMAdapter.chatllm 暴露）。
        if self.chat_agent is None or (
            self.chat is not None
            and getattr(getattr(self.chat_agent, "_provider", None), "chatllm", None) is not self.chat
        ):
            self.chat_agent = self._init_chat_agent()
            if self.chat_agent is not None:
                logger.info("ChatAgent 热重载初始化成功")
        if self.toolllm is None:
            self.toolllm = self._init_toolllm()
            if self.toolllm is not None:
                logger.info("ToolLLM 热重载初始化成功")
        if self.toolllm is not None:
            self.toolllm.rebuild_tool_definitions()

        # 重新初始化消息处理器（唤醒词、权限等配置可能已变更）
        self._init_message_processor()
        logger.info("MessageProcessor 已热重载")

        # 重新初始化 Pipeline（修复 Stage 缓存旧 LLM 引用的问题）
        self._init_pipeline()
        logger.info("Pipeline 已热重载（Stage 引用已更新）")

    @staticmethod
    def _get_planllm_ref():
        """安全获取 PlanLLM 引用（不存在时返回 None，供插件提示词段注入）"""
        try:
            from .llm import get_planllm
            return get_planllm()
        except Exception:
            return None

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
                planllm=self._get_planllm_ref(),
            )
            logger.info(
                "插件管理器初始化完成，已加载 %d 个插件",
                len(self.plugin_manager.list_loaded()),
            )
        except Exception as e:
            logger.warning("插件管理器初始化失败（不影响核心运行）: %s", e)

    def _init_pipeline(self):
        """初始化 StandardPipeline + 9 个 Stage"""
        from core.pipeline import StandardPipeline
        from core.pipeline.stages.build_user_input import BuildUserInputStage
        from core.pipeline.stages.name_mapping import NameMappingStage
        from core.pipeline.stages.session_init import SessionInitStage
        from core.pipeline.stages.context_build import ContextBuildStage
        from core.pipeline.stages.llm_call import LLMCallStage
        from core.pipeline.stages.message_parse import MessageParseStage
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.pipeline.stages.history_save import HistorySaveStage

        self.pipeline = StandardPipeline(bus=bus)

        # 注册 9 个 Stage（按 order 顺序）
        self.pipeline.add_stage(BuildUserInputStage())
        self.pipeline.add_stage(NameMappingStage(
            name_to_id_cache=self._name_to_id,
            id_sanitizer=self._id_sanitizer
        ))
        self.pipeline.add_stage(SessionInitStage(
            session_manager=self.session_manager,
            chat_llm=self.chat,
            bridge=self.bridge
        ))
        self.pipeline.add_stage(ContextBuildStage(
            context_builder=self.context_builder,
            context_buffer=self._chat_context_buffer
        ))
        self.pipeline.add_stage(LLMCallStage(
            chat_llm=self.chat,
            chat_agent=self.chat_agent,
            session_manager=self.session_manager,
            llm_executor=self._llm_executor,
            chat_snapshots=self._chat_snapshots
        ))
        self.pipeline.add_stage(MessageParseStage())
        self.pipeline.add_stage(ToolExecuteStage(
            tool_llm=self.toolllm,
            plan_llm=self._get_planllm_ref(),
            chat_llm=self.chat,
            chat_agent=self.chat_agent,
            session_manager=self.session_manager,
            llm_executor=self._llm_executor,
            chat_snapshots=self._chat_snapshots
        ))
        self.pipeline.add_stage(ReplyDeliverStage(
            adapter_bridge=self.adapter_bridge,
            bridge=self.bridge,
            name_to_id_cache=self._name_to_id,
            id_sanitizer=self._id_sanitizer
        ))
        self.pipeline.add_stage(HistorySaveStage(
            session_manager=self.session_manager,
            chat_llm=self.chat,
            chat_agent=self.chat_agent,
            bridge=self.bridge,
            chat_snapshots=self._chat_snapshots,
            chat_context_buffer=self._chat_context_buffer
        ))

        logger.info("Pipeline 初始化完成（9 个 Stage）")

    def _handle_platform_message(self, event: PlatformEvent):
        """处理平台消息事件（调试用）"""
        platform = event.platform.value
        sender_name = event.sender.name
        text = event.content.text or ""

        logger.debug("[平台消息] [%s] %s: %s", platform, sender_name, text)

    async def _handle_private_message(self, event: PlatformEvent):
        """处理私聊消息"""
        await self._process_message_event(event)

    async def _handle_group_message(self, event: PlatformEvent):
        """处理群消息"""
        await self._process_message_event(event)

    def _handle_qq_message(self, event: PlatformEvent):
        """处理 QQ 特定消息"""
        # 可以在这里添加 QQ 特定的处理逻辑
        pass

    async def _handle_platform_notice(self, event: PlatformEvent):
        """处理平台通知事件（戳一戳、入群、禁言等）"""
        try:
            text = event.content.text or ""
            if text:
                logger.info("[通知] %s", text)
        except Exception as e:
            logger.debug("[通知] 处理通知事件时出错: %s", e)

    async def _handle_wechat_moments_message(self, event: PlatformEvent):
        """处理微信朋友圈消息

        朋友圈动态走 `wechat_moments_message` 通道到达事件总线，
        此处将朋友圈事件转换为消息处理流程，让 LLM 层能感知朋友圈动态。
        """
        await self._process_moments_event(event)

    async def _process_moments_event(self, event: PlatformEvent):
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
            platform = event.platform.value
            sender_name = event.sender.name
            text = event.content.text or ""

            # 从 raw_event 提取额外结构化信息
            raw = event.raw_event or {}
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

            chatllm_reply = await self._call_chatllm(
                user_input, persist_content=user_input, save_to_session=False,
                # 朋友圈是全局通道，无会话标识：ChatAgent 路径沿用
                # self.chat.current_sid（会话消息处理会显式传 sid）
                sid=self.chat.current_sid if self.chat else None,
            )
            # 朋友圈动态不需要发送回复（仅让 LLM 记录到记忆中）
            logger.info("[朋友圈] LLM 已处理 %s 的动态", sender_name)
        except Exception as e:
            logger.error("[朋友圈] 处理朋友圈事件时出错: %s", e, exc_info=True)

    async def _process_message_event(self, event: PlatformEvent):
        """处理消息事件（使用 MessageProcessor 进行决策）

        Args:
            event: PlatformEvent 对象
        """
        # 1. 获取来源适配器实例名（同类多实例时精确路由到正确的那个）
        adapter_instance = getattr(event, 'adapter_instance', None)

        # 2. 使用 MessageProcessor 处理消息
        processed = self.message_processor.process(event)

        # 3. 将消息存入上下文缓冲区（无论决策如何都记录）
        self._store_to_context_buffer(processed)

        # 4. 根据决策处理
        if processed.decision == ResponseDecision.RESPOND:
            # 根据 Feature Flag 选择处理路径
            use_pipeline = config_loader.bot.bot.use_pipeline
            if use_pipeline:
                logger.info("[Pipeline] 使用 StandardPipeline 处理消息")
                await self._handle_respond_message_v2(processed, adapter_instance=adapter_instance)
            else:
                logger.info("[Legacy] 使用旧版流程处理消息")
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
            from .adapter.event import FileAttachment
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
                files=[
                    f if isinstance(f, FileAttachment) else FileAttachment(
                        name=f.get("name", "file"),
                        url=f.get("url", ""),
                        path=f.get("path"),
                        size=f.get("size"),
                    )
                    for f in content_data.get("files", [])
                    if isinstance(f, (FileAttachment, dict))
                ],
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
        # persistence_enabled 时由 SessionManager 管理，不写入 buffer
        persistence = config_loader.bot.bot.persistence_enabled
        if persistence and self.session_manager:
            return
        key = processed.group_id or processed.sender_id
        if not key:
            return
        if not processed.text and not processed.images and not processed.files:
            return

        # 写时复制模式：每次修改都触发 __setitem__，更新 TTL 和 LRU
        import time
        buffer = self._chat_context_buffer.get(key, [])
        buffer.append({
            "sender": processed.sender_name,
            "text": processed.text,
            "time": time.strftime("%H:%M"),
            "images": list(getattr(processed, "images", []) or []),
            "files": [{"name": f.name, "url": f.url, "size": f.size} for f in (getattr(processed, "files", []) or [])],
        })
        # 限制缓冲区大小，防止内存泄漏
        if len(buffer) > 100:
            buffer = buffer[-100:]
        self._chat_context_buffer[key] = buffer  # 触发 __setitem__

    def _check_chatllm_stateless(self) -> bool:
        """检测 ChatLLM 是否支持无状态调用（sid/messages 参数）

        Returns:
            True 如果支持新的无状态模式，False 如果是旧的有状态模式
        """
        if not self.chat:
            return False
        import inspect
        sig = inspect.signature(self.chat.chat)
        return 'sid' in sig.parameters and 'messages' in sig.parameters

    async def _get_session_lock(self, sid: str) -> asyncio.Lock:
        """获取会话专属锁（per-session lock）

        每个会话独立锁，防止同会话消息乱序，不同会话可并发执行。
        使用 BoundedCache 存储锁对象，自动淘汰过期会话的锁。

        Args:
            sid: 会话标识

        Returns:
            该会话的独立锁
        """
        async with self._session_locks_lock:
            lock = self._session_locks.get(sid)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[sid] = lock
            return lock

    def _get_chat_lock(self) -> asyncio.Lock:
        """向后兼容方法（已废弃，保留以防其他代码调用）"""
        # 返回一个假锁，实际不再使用全局锁
        import warnings
        warnings.warn("_get_chat_lock is deprecated, use per-session locks instead", DeprecationWarning)
        return asyncio.Lock()

    def _download_ctx_image(self, url_or_path: str) -> Optional[str]:
        """下载上下文窗口中的图片到本地临时目录。

        如果是本地路径直接返回；远程 URL 下载到 data/temp/ctx_images/。
        """
        local_path = Path(url_or_path)
        if local_path.is_file():
            return str(local_path.resolve())

        if not url_or_path.startswith(('http://', 'https://')):
            return None

        # SSRF 防护：用 safe_get 把连接固定到已校验 IP（消除 TOCTOU / DNS rebinding），
        # 并逐跳重新校验重定向目标。
        from core.tools.network_safety import safe_get, SSRFValidationError

        import hashlib
        import os
        from urllib.parse import urljoin
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

        MAX_IMAGE_BYTES = 5 * 1024 * 1024
        resp = None
        try:
            current_url = url_or_path
            for _ in range(5):  # 最多跟随 4 次重定向，每跳重新校验+固定 IP
                resp = safe_get(current_url, requests_mod=requests, timeout=10, stream=True)
                if resp.is_redirect and resp.headers.get("location"):
                    next_url = urljoin(current_url, resp.headers["location"])
                    resp.close()
                    current_url = next_url
                    continue
                break
            resp.raise_for_status()
            content_length = resp.headers.get('content-length')
            if content_length and int(content_length) > MAX_IMAGE_BYTES:
                logger.warning("图片过大，跳过下载: %s (%s)", url_or_path, content_length)
                return None
            # 即使响应未声明 content-length，也按上限边下边截断，防止无界下载
            total = 0
            with open(dest, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    total += len(chunk)
                    if total > MAX_IMAGE_BYTES:
                        logger.warning("图片超出大小上限，中止下载: %s", url_or_path)
                        f.close()
                        dest.unlink(missing_ok=True)
                        return None
                    f.write(chunk)
            return str(dest)
        except SSRFValidationError as e:
            logger.warning("SSRF 安全检查未通过，跳过图片下载: %s", e)
            dest.unlink(missing_ok=True)
            return None
        except Exception as e:
            # 异常时清掉可能的半成品文件，避免被 dest.is_file() 缓存命中复用损坏数据
            logger.warning("下载上下文图片失败 %s: %s", url_or_path, e)
            dest.unlink(missing_ok=True)
            return None
        finally:
            if resp is not None:
                resp.close()

    async def _build_context_window(self, processed: ProcessedMessage, window: int) -> str:
        """从缓冲区获取最近 N 条消息作为上下文，图片自动 VLM 识别。

        排除缓冲区末条（即当前消息）以避免与直连 VLM 路径重复识别同一张图。
        下载与 VLM 调用均为阻塞操作，offload 到 _llm_executor 避免阻塞事件循环。
        """
        key = processed.group_id or processed.sender_id
        if not key or not self._chat_context_buffer.get(key):
            return ""
        # 末条是当前消息，直连路径已识别其图片，这里只看历史
        recent = self._chat_context_buffer[key][-(window + 1):-1]
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
        # 用专用 executor：本方法被 per-session 锁内调用，若用默认 executor
        # 提交阻塞任务（图片下载/VLM），同一批并发消息会互相占住默认池线程，
        # 高并发下排队等待可能导致响应延迟（ChatAgent 专用池同理由）
        executor = self._chat_agent_executor
        lines = []
        img_count = 0
        max_ctx_images = 2

        for msg in recent:
            text = msg.get('text') or ''
            file_names = ", ".join(f.get('name', '') for f in (msg.get('files') or [])[:3])
            if text:
                # 带文本的消息也要保留文件名，否则 AI 不知道曾有文件被分享
                line = f"[{msg['sender']}] {text}".rstrip()
                if file_names:
                    line += f" [文件: {file_names}]"
            elif file_names:
                line = f"[{msg['sender']}] [文件: {file_names}]"
            else:
                line = f"[{msg['sender']}] [图片]"

            # 历史消息有图片且 VLM 可用时自动识别
            if vlm_available and msg.get('images') and img_count < max_ctx_images:
                for img_url in msg['images']:
                    if img_count >= max_ctx_images:
                        break
                    local_path = await loop.run_in_executor(
                        executor, self._download_ctx_image, img_url
                    )
                    if local_path:
                        try:
                            desc = await loop.run_in_executor(
                                executor,
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
        """处理需要响应的消息（旧版流程）

        Args:
            processed: 处理后的消息
            adapter_instance: 来源适配器实例名，用于同类多实例精确路由
        """
        # 构造会话ID用于日志
        platform_name = processed.platform.value if processed.platform else "unknown"
        sid_for_log = f"{platform_name}:{'gm' if processed.group_id else 'dm'}:{processed.group_id or processed.sender_id}"
        logger.info("[Legacy Path] 处理消息: sid=%s, sender=%s", sid_for_log, processed.sender_name)
        # ================================================================
        # 格式化用户消息（结构化格式）
        # ================================================================
        # 平台
        platform_name = processed.platform.value if processed.platform else adapter_instance or "unknown"

        # 构建消息主体：[At xxx] [Reply xxx] 内容
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
        user_text = " ".join(msg_parts)

        # ================================================================
        # 构建结构化上下文（分段清晰）
        # ================================================================
        import datetime
        now = datetime.datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")

        # ID脱敏：用户ID和群ID打码，防止AI泄露敏感信息
        masked_sender_id = self._id_sanitizer.sanitize_user_id(processed.sender_id)

        sections = []

        # 1. 时间信息
        sections.append(f"[当前时间] {time_str}")

        # 2. 消息元数据（使用列表格式 + ID脱敏）
        metadata_lines = ["[消息元数据]"]
        metadata_lines.append(f"- 消息ID: {processed.message_id}")
        metadata_lines.append(f"- 发送者: {processed.sender_name} ({masked_sender_id})")
        if processed.is_group_message:
            masked_group_id = self._id_sanitizer.sanitize_group_id(processed.group_id)
            if processed.group_name:
                metadata_lines.append(f"- 群组: {processed.group_name} ({masked_group_id})")
            else:
                metadata_lines.append(f"- 群组ID: {masked_group_id}")
            chat_type = "群聊"
        else:
            chat_type = "私聊"
        sections.append("\n".join(metadata_lines))

        # 3. 环境信息
        env_lines = ["[环境信息]"]
        env_lines.append(f"- 平台: {platform_name}")
        env_lines.append(f"- 类型: {chat_type}")
        sections.append("\n".join(env_lines))

        # 4. 富媒体信息
        extra_media = []
        if processed.voices:
            extra_media.append(f"- 语音消息: {len(processed.voices)} 条")
        if processed.faces:
            extra_media.append(f"- QQ表情: {len(processed.faces)} 个")
        if processed.stickers:
            extra_media.append(f"- 动画表情: {len(processed.stickers)} 个")
        if processed.videos:
            extra_media.append(f"- 视频: {len(processed.videos)} 个")
        if processed.files:
            file_names = ", ".join(f.name for f in processed.files[:5])
            extra_media.append(f"- 文件: {len(processed.files)} 个 ({file_names})")
        if extra_media:
            sections.append("[附件信息]\n" + "\n".join(extra_media))

        # user_input 初始值（稍后会追加图片识别、上下文、跨会话消息等）
        user_input = "\n\n".join(sections)

        # 维护昵称→ID 映射表（按群分组，供发送时解析 @ 用）
        # 注意：这里存储的是打码后的ID，发送时需要还原
        if processed.sender_name and processed.sender_id:
            group_key = processed.group_id or "_private"
            # 写时复制模式：每次修改都触发 __setitem__，更新 TTL 和 LRU
            name_map = self._name_to_id.get(group_key, {})
            name_map[processed.sender_name] = masked_sender_id  # 存储打码ID
            self._name_to_id[group_key] = name_map  # 触发 __setitem__

        logger.info("处理 %s (%s): %s", processed.sender_name, processed.reason, processed.text)

        is_group = processed.group_id is not None
        target_id = processed.group_id if processed.group_id else processed.sender_id

        # 构造会话标识（set_session 移入锁内，防跨会话串味）
        persistence = config_loader.bot.bot.persistence_enabled
        sid = None
        session_enabled = True
        if persistence and self.session_manager and self.chat:
            stype = "gm" if is_group else "dm"
            sid = f"{processed.platform.value}:{stype}:{target_id}"
            session_obj = self.session_manager.get_or_create(sid)
            session_enabled = session_obj.enabled
        elif self.chat:
            # 即使未启用持久化，也需生成 sid 用于 per-session 锁隔离
            stype = "gm" if is_group else "dm"
            sid = f"{processed.platform.value}:{stype}:{target_id}"

        try:
            # Semaphore 限流：控制全局最大并发 LLM 调用数
            async with self._session_semaphore:
                # per-session 锁：每个会话独立锁，防止同会话消息乱序
                session_lock = await self._get_session_lock(sid)
                async with session_lock:
                    # set_session 在锁内执行，确保 self.messages/current_sid 原子化。
                    # ChatAgent 模式（无状态）下 set_session 仅用于绑定会话 ID，
                    # 历史由 SessionManager 统一管理、调用时按需传入。
                    if sid:
                        self.chat.set_session(sid, load_history=session_enabled)
                    # ── 跨会话消息注入（consume inbox） ──
                    inbox_msgs = []
                    cross_session_text = ""
                    accessible_sessions_text = ""
                    if sid and self.bridge:
                        inbox_msgs = await self.bridge.consume(sid)
                        if inbox_msgs:
                            inbox_lines = ["[来自其他会话的消息]"]
                            for m in inbox_msgs:
                                inbox_lines.append(f"- 来自 {m['from_sid']}: {m['content'][:200]}")
                            cross_session_text = "\n".join(inbox_lines)
                        # 注入可通信会话列表（最多 5 个）
                        accessible = self.bridge.list_accessible(sid)
                        if accessible:
                            sess_list = ", ".join(accessible)
                            accessible_sessions_text = f"[可通信会话] {sess_list}"

                    # 有图片时直接用 VLM 识别，结果注入上下文供 ChatLLM 感知
                    image_recognition_text = ""
                    if processed.images:
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
                                image_recognition_text = f"[图片识别结果]\n{vlm_result}"
                        except Exception as e:
                            logger.warning("VLM 图片识别失败: %s", e)

                    # 追加滑动上下文窗口
                    # persist_content = 拼接历史前的 user_input（纯净用户消息，用于落库）
                    # 注意：persist_content 需要在最终组装前保存基础内容
                    context_text = ""
                    use_ctx = bool(processed.text and not (
                        persistence and self.session_manager and sid and session_enabled
                    ))
                    if use_ctx:
                        ctx_window_cfg = config_loader.bot.context
                        if ctx_window_cfg.chat_context_enabled and ctx_window_cfg.chat_context_window > 0:
                            ctx = await self._build_context_window(processed, ctx_window_cfg.chat_context_window)
                            if ctx:
                                logger.debug("追加上下文窗口 (%d 条)", ctx_window_cfg.chat_context_window)
                                context_text = f"---\n以下是最近的聊天记录：\n{ctx}\n---"
                    # set_session 已通过 self.messages 结构化加载历史，无需额外拼接

                    # ================================================================
                    # 最终组装：按优先级排列各个段落
                    # ================================================================
                    final_sections = [user_input]  # 基础元数据（时间、消息、环境）

                    # 附加信息按重要性排列
                    if image_recognition_text:
                        final_sections.append(image_recognition_text)

                    if context_text:
                        final_sections.append(context_text)

                    # 当前用户消息作为重点（放在明显位置）
                    final_sections.append(f"## 当前消息\n{user_text}")

                    # 跨会话消息作为补充信息
                    if cross_session_text:
                        final_sections.append(cross_session_text)

                    if accessible_sessions_text:
                        final_sections.append(accessible_sessions_text)

                    # 组装最终输入
                    user_input = "\n\n".join(final_sections)

                    # persist_content 用于落库，只包含核心消息内容
                    persist_content = user_text

                    # 首次调用不落库（save_to_session=False），最终回复在最后统一持久化
                    # 避免工具调用轮次和最终回复双重写入
                    chatllm_reply = await self._call_chatllm(
                        user_input, persist_content, save_to_session=False, sid=sid
                    )
                    parsed = parse_xml_msg(chatllm_reply)

                    async def _persist_and_ack():
                        # 本轮跨会话消息已被 consume 移入 pending；无论以何种路径结束
                        # （含 skip_reply / 解析失败 / 纯文本回复等提前 return），
                        # 都需落库并 ack，否则这些消息会被判超时重复投递，回退回复也不会写入记忆。
                        if self.chat_agent is not None and sid:
                            # ChatAgent 路径：无状态，最终回复从快照统一落库
                            # （user 纯净原文 + 最终 assistant 回复，与旧语义一致）
                            self._persist_snapshot(sid)
                        elif self.chat and self.chat.current_sid and persist_content:
                            self.chat._save_session_memory(persist_content)
                        if inbox_msgs and sid and self.bridge:
                            _mids = [m["id"] for m in inbox_msgs if m.get("id")]
                            if _mids:
                                await self.bridge.ack(sid, _mids)

                    # AI 使用 <msg></msg> 主动结束对话，不发送任何消息
                    if parsed.get("skip_reply") and not parsed.get("messages") and not self._has_tool_content(parsed):
                        logger.info("AI 选择不回复消息 (skip_reply) -> %s", target_id)
                        await _persist_and_ack()
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
                        await _persist_and_ack()
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
                        await _persist_and_ack()
                        return

                    if needs_follow_up:
                        # 多轮对话：先发送首条回复
                        await self._send_message_batch(
                            processed, first_messages[:MAX_SPLIT_COUNT], adapter_instance=adapter_instance
                        )
                        # 执行后续操作并获取最终回复
                        final_messages = await self._resolve_follow_up(chatllm_reply, parsed, sid=sid)
                        await self._send_message_batch(
                            processed, final_messages[:MAX_SPLIT_COUNT], adapter_instance=adapter_instance
                        )
                    else:
                        # 普通回复直接发送
                        await self._send_message_batch(
                            processed, first_messages[:MAX_SPLIT_COUNT], adapter_instance=adapter_instance
                        )

                    # ── 处理跨会话消息：解析 session_send 标签并异步投递 ──
                    _pending_sends = []
                    for ss in parsed.get("session_sends", []):
                        target = ss.get("target", "").strip()
                        text = ss.get("text", "").strip()
                        if target and text and sid and self.bridge:
                            _pending_sends.append(asyncio.create_task(
                                self._send_cross_session(sid, target, text)
                            ))

                    # ── B1: 统一持久化最终回复 + ack 跨会话消息 ──
                    # 首次 chat() 用 save_to_session=False 不落库，这里统一持久化；
                    # needs_follow_up 存 Agent 循环后的最终回复，否则存首条回复。
                    await _persist_and_ack()

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
        # session_lock 和 semaphore 由 async with 自动释放

    @staticmethod
    def _compute_session_info(processed: ProcessedMessage) -> tuple:
        """计算会话信息（sid, is_group, target_id, platform_name）

        从 ProcessedMessage 提取会话标识所需的各项信息，避免重复计算逻辑。

        Args:
            processed: ProcessedMessage 对象

        Returns:
            (sid, is_group, target_id, platform_name) 元组
        """
        is_group = processed.group_id is not None
        target_id = processed.group_id if processed.group_id else processed.sender_id
        stype = "gm" if is_group else "dm"
        platform_name = processed.platform.value if processed.platform else "unknown"
        sid = f"{platform_name}:{stype}:{target_id}"
        return sid, is_group, target_id, platform_name

    async def _handle_respond_message_v2(self, processed, adapter_instance=None):
        """处理需要响应的消息（Pipeline 版本，带并发控制）

        修复 P0-1: 添加 Semaphore + per-session lock 并发控制
        """
        from core.pipeline import PipelineContext

        # 1. 计算会话信息（使用提取的静态方法）
        sid, is_group, target_id, platform_name = self._compute_session_info(processed)
        if adapter_instance:
            platform_name = adapter_instance

        logger.info("[Pipeline Path] 处理消息: sid=%s, sender=%s", sid, processed.sender_name)

        # 2. 构造 PipelineContext
        ctx = PipelineContext(
            processed=processed,
            adapter_instance=adapter_instance,
            sid=sid,
            is_group=is_group,
            target_id=target_id,
            platform_name=platform_name
        )

        # 3. 添加并发控制（与原实现一致）
        try:
            async with self._session_semaphore:  # 全局限流
                session_lock = await self._get_session_lock(sid)
                async with session_lock:  # per-session 锁
                    await self.pipeline.execute(ctx)
        except Exception as e:
            logger.error("Pipeline 处理消息失败: %s", e, exc_info=True)
            # 发送错误回显给用户
            error_msg = f"[系统] 处理消息时出了点状况：{e}"
            await self._send_reply(
                adapter_instance or processed.platform.value,
                target_id,
                error_msg,
                reply_to=processed.message_id,
                is_group=is_group
            )

    async def _send_cross_session(self, from_sid: str, to_sid: str, text: str):
        """主动推送跨会话消息

        流程：
        1. bridge.send 做权限校验 + 限流 + 写 inbox（持目标锁，释放后返回）
        2. 解析 to_sid，通过 adapter_bridge 真实发送 QQ 消息（不持锁）
        3. 推送成功后 ack 标记已处理，避免目标会话 consume 时重复注入
        4. 失败时反向写系统消息到源会话 inbox，AI 下轮可感知

        复用 bridge.send 的权限/限流校验，主动推送不绕过安全策略。
        """
        try:
            # 1. 权限 + 限流 + 写 inbox（send 内部持目标锁，释放后返回）
            result = await asyncio.wait_for(
                self.bridge.send(from_sid, to_sid, text),
                timeout=10,
            )
            if result.startswith("error:"):
                logger.warning("跨会话权限/限流拒绝: %s → %s: %s", from_sid, to_sid, result)
                # 失败反馈直接写源会话 inbox，绕过权限/限流校验，
                # 避免反向 bridge.send 因对称权限拒绝而静默丢失提示
                await self.bridge.add_system_message(from_sid, f"[系统] 跨会话发送失败：{result[6:]}")
                return
            msg_id = result

            # 2. 主动推送：解析 sid，通过适配器真实发送（不持任何会话锁）
            parts = to_sid.split(":", 2)
            if len(parts) == 3 and self.adapter_bridge:
                adapter_name, stype, target_id = parts

                # 还原打码ID：AI可能输出 usr_1001 或 grp_1002，需要还原为真实ID
                if target_id.startswith("usr_"):
                    target_id = self._id_sanitizer.restore_user_id(target_id)
                elif target_id.startswith("grp_"):
                    target_id = self._id_sanitizer.restore_group_id(target_id)

                # 校验 target_id 必须是纯数字（群号/QQ号），拒绝群名/占位符
                if not target_id.isdigit():
                    logger.warning("跨会话 sid 的 id 非数字: %s", to_sid)
                    # 失败反馈走内部投递，绕过对称权限/限流，避免静默丢失
                    await self.bridge.add_system_message(
                        from_sid,
                        f"[系统] 跨会话发送失败：id 必须是纯数字群号或用户号，收到 '{target_id}'"
                    )
                    await self.bridge.ack(to_sid, [msg_id])
                    return
                result = await self.adapter_bridge.send_message(
                    adapter_id=adapter_name,
                    target_id=target_id,
                    text=text,
                    is_group=(stype == "gm"),
                )
                success = bool(result)
                logger.info("跨会话主动推送: %s → %s (success=%s)", from_sid, to_sid, success)
                # 3. 推送成功后立即 ack，避免目标会话 consume 时重复注入
                if success:
                    await self.bridge.ack(to_sid, [msg_id])
                else:
                    logger.warning("跨会话推送失败，消息保留在 inbox: %s → %s", from_sid, to_sid)
            else:
                logger.warning("跨会话 sid 格式无效: %s", to_sid)
        except asyncio.TimeoutError:
            logger.warning("跨会话发送超时: %s → %s", from_sid, to_sid)
        except Exception as e:
            logger.error("跨会话发送异常: %s → %s: %s", from_sid, to_sid, e, exc_info=True)

    async def _send_message_batch(self, processed: ProcessedMessage, messages: list, adapter_instance: str = None):
        """批量发送消息，每条消息前模拟打字延迟（包括第一条），句间额外停顿"""
        is_group = processed.group_id is not None
        target_id = processed.group_id if processed.group_id else processed.sender_id
        inter_delay = getattr(config_loader.bot.bot, 'typing_inter_delay', 2.0)
        all_failed_files = []
        for idx, msg in enumerate(messages):
            reply_text = self._extract_message_text(msg)
            if reply_text or msg.images or msg.files:
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
                            # 如果AI输出了打码ID（usr_xxx），还原为真实ID
                            if self._id_sanitizer.is_masked_user_id(qq_id):
                                qq_id = self._id_sanitizer.restore_user_id(qq_id)
                            at_list.append(qq_id)
                    if at_list:
                        at_targets = at_list
                # AI 可主动通过 <reply> 指定引用回复的消息 ID；
                # 不写 <reply> 则不引用（而非默认引用当前消息）
                reply_to = msg.reply_to or None
                failed = await self._send_reply(
                    adapter_instance or processed.platform.value,
                    target_id,
                    reply_text,
                    reply_to=reply_to,
                    is_group=is_group,
                    at_targets=at_targets,
                    images=msg.images or None,
                    files=msg.files or None,
                )
                all_failed_files.extend(failed or [])
                # 句与句之间的额外停顿（最后一条不等待）
                if idx < len(messages) - 1:
                    await asyncio.sleep(inter_delay)
        # 文件发送失败通知：注入到当前 session 上下文供 AI 感知
        if all_failed_files:
            self._notify_file_upload_failure(processed, all_failed_files)

    def _notify_file_upload_failure(self, processed: ProcessedMessage, failed_files: list):
        """将文件发送失败信息注入 AI 上下文"""
        file_list = "、".join(failed_files[:5])
        notice = f"[系统通知] 文件发送失败：{file_list}"
        persistence = config_loader.bot.bot.persistence_enabled
        # 与 _store_to_context_buffer 相同的判定：持久化模式下 buffer 无人读取
        # （use_ctx 恒为 False）且不经过截断，写入只会造成内存无限增长
        use_buffer = not (persistence and self.session_manager)

        # 写入上下文缓冲区（插入到当前消息之前，避免被 [:-1] 跳过）
        key = processed.group_id or processed.sender_id
        if key and use_buffer:
            entries = self._chat_context_buffer.setdefault(key, [])
            entry = {
                "sender": "系统",
                "text": notice,
                "time": time.strftime("%H:%M"),
                "images": [],
                "files": [],
            }
            entries.insert(max(len(entries) - 1, 0), entry)

        # 持久化路径：写入会话记忆，供下次 set_session 时 AI 感知
        if persistence and self.session_manager and self.chat and self.chat.current_sid:
            # append_memory 需要 user+assistant 均非空，用占位保证配对完整性
            self.session_manager.append_memory(
                self.chat.current_sid,
                {"role": "user", "content": notice},
                {"role": "assistant", "content": "（文件上传失败通知已被记录）"},
            )
        logger.info("已注入文件发送失败通知: %s", notice)

    @staticmethod
    def _has_tool_content(parsed: dict, raw_reply: str = "") -> bool:
        """检查解析结果中是否还有待处理的工具/动作/计划/FC 内容"""
        if parsed.get("actions") or parsed.get("plan"):
            return True
        if raw_reply and parse_function_call(raw_reply) is not None:
            return True
        return False

    async def _call_chatllm_with_timeout(self, user_input: str, timeout: float,
                                          persist_content: str = None,
                                          save_to_session: bool = True,
                                          sid: str = None) -> str:
        """带超时的 ChatLLM 调用

        Args:
            user_input: 用户输入
            timeout: 超时秒数
            persist_content: 落库用纯净原文，None 则用 user_input
            save_to_session: 是否写入会话记忆，Agent 内部步骤应传 False
            sid: 会话标识（Agent 内部步骤必须显式传入；无持久化模式下
                self.chat.current_sid 为 None，缺省会落到空 sid，
                工具轮次将读不到/写不进快照，丢失上下文）

        Returns:
            AI 回复文本，超时时返回错误提示
        """
        if not user_input:
            return ""
        try:
            return await asyncio.wait_for(
                self._call_chatllm(user_input, persist_content, save_to_session, sid=sid),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning("AgentExecutor 步骤超时 (%.1fs)", timeout)
            timeout_msg = "[系统] 思考时间较长，已自动结束当前推理。"
            return f"<msg><text>{timeout_msg}</text></msg>"

    async def _resolve_follow_up(self, chatllm_reply: str, parsed: Optional[dict] = None,
                                 sid: str = None) -> list:
        """
        AgentExecutor 多步骤推理循环。

        每轮执行当前回复中所有待处理的工具/动作/计划/FC，
        将结果汇总回送 ChatLLM，重复直到达到最大轮数或没有更多工具内容。

        Args:
            chatllm_reply: 首轮 ChatLLM 原始回复
            parsed: 解析结果，None 时内部解析
            sid: 会话标识；工具轮次必须携带，保证 ChatAgent 路径的
                快照读写（上下文连续）与旧路径语义一致
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

            # Phase C: <plan> 标签
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
            current_reply = await self._call_chatllm_with_timeout(
                follow_up_prompt, per_step_timeout,
                persist_content=None, save_to_session=False,
                sid=sid,
            )
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
                f"可以继续使用 <act>/<plan> 标签。"
            )
        else:
            return (
                f"[Agent 第 {iteration}/{max_steps} 轮 — 最后一轮] {title}：\n"
                f"{result}\n\n"
                f"这是最后一轮推理。请根据已有信息给用户一个完整回复，"
                f"不要再使用 <act>/<plan> 标签。"
            )

    async def _execute_actions(self, actions: list) -> list:
        """执行动作列表，返回所有执行结果。工具不存在时自动返回可用工具列表。"""
        results = []
        # ToolLLM 未配置 API Key 时为 None，无法生成 Function Calling，直接降级
        if self.toolllm is None:
            logger.warning("ToolLLM 未初始化，跳过 %d 个动作", len(actions))
            return ["工具能力未配置，无法执行该动作。"]
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

                # 工具执行失败时，检查是否为"未知的函数"错误，自动返回工具列表
                if isinstance(tool_result, dict) and tool_result.get("status") == "failed":
                    error_msg = tool_result.get("error", "")
                    if "未知的函数" in error_msg:
                        logger.info("工具不存在，返回可用工具列表")
                        tools_list = self.toolllm.query_tools()
                        tool_result = {
                            "status": "failed",
                            "error": error_msg,
                            "available_tools": tools_list,
                            "message": f"工具不存在。当前可用工具：\n{tools_list}"
                        }

                results.append(tool_result)
            else:
                logger.warning("无法解析 Function Calling")
        return results


    def _get_session_messages(self, sid: str) -> List[Dict]:
        """组装 ChatAgent 模式的会话消息列表（#183）。

        ChatAgent 无状态：历史消息在每次调用时传入，由 SessionManager 统一管理。
        此处将会话历史与当前快照（本轮追加段）合并：
        - system 头由 ChatLLMAdapter 显式注入（_prepend_system_head，P1）
        - 持久化模式：历史来自 SessionManager.get_memory(sid)
        - 快照缓存本轮未落库的追加消息（Agent 多轮循环上下文连续）；
          无持久化模式下快照在 _persist_snapshot 中每轮清空（P2），不跨轮读取

        Returns:
            消息列表（[{role, content}, ...]）
        """
        messages: List[Dict] = []
        if self.session_manager is not None:
            try:
                # 禁用的会话不加载历史（与旧路径 set_session(sid,
                # load_history=session_enabled) 语义一致）：否则会把已存储
                # 的历史又发给 LLM，禁用形同虚设
                session = self.session_manager.get_session(sid)
                if session is None or session.enabled:
                    messages.extend(self.session_manager.get_memory(sid))
            except Exception as e:
                logger.debug("读取会话历史失败: %s", e)
        messages.extend(self._chat_snapshots.get(sid, []))
        return messages

    def _persist_snapshot(self, sid: str):
        """将 ChatAgent 模式的会话快照落库到 SessionManager（#183）

        快照中 user+assistant 成对写入（与旧路径 _save_session_memory 语义一致），
        落库成功后清空快照，避免下次轮次重复追加。

        无持久化模式（session_manager 为 None）下无库可落：快照只承载
        本轮追加段，直接清空即可（下轮从头开始），否则快照只进不出，
        每条消息都带上此前所有消息原文，造成上下文漂移（P2）。
        """
        if not sid:
            return
        if self.session_manager is None:
            self._chat_snapshots.pop(sid, None)
            return
        try:
            session = self.session_manager.get_session(sid)
            if session is not None and not session.enabled:
                return  # 禁用的会话不持久化新记忆
            snap = self._chat_snapshots.get(sid, [])
            i = 0
            while i < len(snap) - 1:
                if snap[i].get("role") == "user" and snap[i + 1].get("role") == "assistant":
                    self.session_manager.append_memory(
                        sid,
                        {"role": "user", "content": snap[i].get("content", "")},
                        {"role": "assistant", "content": snap[i + 1].get("content", "")},
                    )
                    i += 2
                else:
                    i += 1
            self._chat_snapshots.pop(sid, None)
        except Exception as e:
            logger.debug("会话快照落库失败: %s", e)

    async def _call_chatllm(self, user_input: str, persist_content: str = None,
                             save_to_session: bool = True, sid: str = None) -> str:
        """调用 LLM 生成回复（非阻塞，使用线程池执行同步 API 调用）

        #183 集成：优先走无状态 ChatAgent.generate(messages, session_id, timeout)，
        ChatAgent 内部自带 per-session lock + Semaphore 并发控制与超时保护。
        历史消息由 SessionManager 统一管理，调用时组装传入。

        Args:
            user_input: 发给 LLM 的用户输入
            persist_content: 落库时存入会话记忆的纯净用户原文，None 则用 user_input
            save_to_session: 是否写入会话记忆，Agent 内部步骤传 False
            sid: 会话标识（ChatAgent 路径必须显式传入；无持久化模式下
                self.chat.current_sid 可能为 None，需用锁内的 sid）

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
            if self.chat_agent is not None:
                # ── ChatAgent 无状态路径 ──
                # 历史由 SessionManager 统一管理，调用时从会话历史+快照组装；
                # 当前用户消息作为 user 消息传入（system 头由 ChatLLMAdapter
                # 显式补齐，见 _prepend_system_head）
                if not sid:
                    sid = self.chat.current_sid or ""
                messages = self._get_session_messages(sid)
                messages.append({"role": "user", "content": user_input})
                reply = await self.chat_agent.generate(
                    messages=messages,
                    session_id=sid,
                    timeout=60.0,
                )
                if reply is None:
                    logger.error("ChatLLM API 返回空响应")
                    reply = ""
                # 本轮追加段入快照（最终回复由 _persist_and_ack 统一落库）。
                # 工具轮次（persist_content=None）只更新回复，保留首条用户原文，
                # 与旧路径 _save_session_memory 语义一致（落库纯净原文 + 最终回复）。
                # 无持久化模式（session_manager 为 None）下快照在 _persist_snapshot
                # 中每轮清空，本轮追加段不跨轮读取（P2）。
                if (reply or persist_content) and sid:
                    # 空 sid（控制台模式）不建快照：无 _persist_and_ack 调用，
                    # 建了只会残留无界增长（P2）
                    snap = self._chat_snapshots.setdefault(sid, [])
                    if persist_content:
                        snap.append({"role": "user", "content": persist_content or user_input})
                    if reply:
                        if snap and snap[-1].get("role") == "assistant":
                            snap[-1] = {"role": "assistant", "content": reply}
                        else:
                            snap.append({"role": "assistant", "content": reply})
                    # 快照只承载本轮未落库的追加段，限制长度防内存泄漏
                    if len(snap) > 40:
                        self._chat_snapshots[sid] = snap[-20:]
            else:
                # ── 兼容路径：ChatLLM 有状态调用 ──
                reply = await loop.run_in_executor(
                    self._llm_executor, self.chat.chat, user_input, persist_content, save_to_session
                )
        finally:
            # 停止动画（daemon 线程无需 join，进程退出时自动终止）
            stop_event.set()

        return reply

    async def _generate_reply(self, user_input: str) -> list:
        """生成 AI 回复（控制台模式入口）

        Args:
            user_input: 用户输入

        Returns:
            消息对象列表
        """
        if not user_input:
            return []

        chatllm_reply = await self._call_chatllm(user_input, persist_content=user_input)
        return await self._resolve_follow_up(chatllm_reply, sid=self.chat.current_sid if self.chat else None)

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
        files: Optional[list] = None,
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
            files: 文件附件列表（可选，FileAttachment 或 dict）
        """
        if not self.adapter_bridge or (not reply and not images and not files):
            return

        try:
            send_kwargs = dict(
                adapter_id=platform,
                target_id=target_id,
                text=reply,
                images=images,
                reply_to=reply_to,
                is_group=is_group,
                at_targets=at_targets,
            )
            if files:
                send_kwargs["files"] = files
            result = await self.adapter_bridge.send_message(**send_kwargs)
            success = bool(result)
            failed_files = result.failed_files
            if success:
                logger.info("发送成功 [%s] -> %s", platform, target_id)
            else:
                logger.warning("发送失败 [%s] -> %s", platform, target_id)
            if failed_files:
                logger.warning("[文件发送失败] %s -> %s: %s", platform, target_id, failed_files)
            return failed_files
        except Exception as e:
            logger.error("发送错误: %s", e)
            # 异常时所有文件视为未送达，保证失败通知能触发
            return [
                (f.name if hasattr(f, "name") else f.get("name", "file"))
                for f in (files or [])
            ]

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
                # 注意：存储打码后的ID，保持与消息元数据一致
                group_key = group_id
                # 写时复制模式：每次修改都触发 __setitem__，更新 TTL 和 LRU
                name_map = self._name_to_id.get(group_key, {})
                for m in members:
                    uid = m.get("user_id", "")
                    nick = m.get("nickname", "")
                    if uid and nick:
                        masked_uid = self._id_sanitizer.sanitize_user_id(str(uid))
                        name_map[nick] = masked_uid
                self._name_to_id[group_key] = name_map  # 触发 __setitem__
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

            # 注册查询群列表工具
            def _run_query_group_list(parameters):
                future = asyncio.run_coroutine_threadsafe(
                    QQApiClient.get_group_list(), _loop
                )
                try:
                    groups = future.result(timeout=30)
                except Exception as e:
                    return {"status": "failed", "error": f"查询群列表失败: {e}"}
                if not groups:
                    return {"status": "ok", "groups": [], "message": "机器人未加入任何群"}

                # 对群ID打码，防止AI泄露真实群号
                masked_groups = []
                for group in groups:
                    masked_group = group.copy()
                    if "group_id" in masked_group:
                        masked_group["group_id"] = self._id_sanitizer.sanitize_group_id(
                            str(masked_group["group_id"])
                        )
                    masked_groups.append(masked_group)

                return {
                    "status": "ok",
                    "groups": masked_groups,
                    "message": f"机器人加入了 {len(masked_groups)} 个群",
                }

            register_plugin_handler("query_group_list", _run_query_group_list)

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
            get_registry().register(
                ToolDefinition(
                    name="query_group_list",
                    description="获取机器人加入的所有群聊列表，返回群号和群名称。无需参数。",
                    parameters=[],
                )
            )

            # 注册工具统计诊断工具
            def _run_tool_stats(parameters):
                from core.function_caller import get_tool_stats
                stats = get_tool_stats()

                # 格式化输出
                lines = [f"总调用次数: {stats['total_calls']}"]
                lines.append(f"成功: {stats['success_count']}, 失败: {stats['failure_count']}")

                if stats['by_tool']:
                    lines.append("\n工具统计:")
                    for tool_name, tool_stat in sorted(stats['by_tool'].items(),
                                                       key=lambda x: x[1]['calls'],
                                                       reverse=True):
                        avg_time = tool_stat['total_time_ms'] / tool_stat['calls'] if tool_stat['calls'] > 0 else 0
                        lines.append(f"  {tool_name}: {tool_stat['calls']}次调用, "
                                    f"成功{tool_stat['success']}次, "
                                    f"失败{tool_stat['failure']}次, "
                                    f"平均{avg_time:.0f}ms")
                else:
                    lines.append("\n暂无工具调用记录")

                return {"status": "success", "result": "\n".join(lines)}

            register_plugin_handler("tool_stats", _run_tool_stats)

            get_registry().register(
                ToolDefinition(
                    name="tool_stats",
                    description="查询工具使用统计，包括调用次数、成功率、平均耗时等。无需参数。",
                    parameters=[],
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

        # 释放线程池：wait=False 立即返回，残留的阻塞线程不会拖住进程退出
        # （ThreadPoolExecutor 线程非 daemon，若 wait=True 会被慢调用卡住）
        if self._llm_executor is not None:
            self._llm_executor.shutdown(wait=False, cancel_futures=True)
        if self._chat_agent_executor is not None:
            self._chat_agent_executor.shutdown(wait=False, cancel_futures=True)

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
