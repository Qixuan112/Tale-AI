from typing import Optional

import threading
from ..bus import bus
from ..config import MAX_CONTEXT
from ..config.provide import get_character_prompt, get_dialogue_examples, config_loader
from ..utils import get_logger
from .context import AgentContext, create_chat_context
from .context.section import PromptSection
from .provider import OpenAICompatibleProvider, provider_manager

logger = get_logger(__name__)


class ChatLLM:
    def __init__(self, api_key, model, url, max_context=MAX_CONTEXT,
                 context: Optional[AgentContext] = None,
                 cache_strategy: str = "single_message"):
        """
        初始化 ChatLLM

        Args:
            api_key: OpenAI API 密钥
            model: 使用的模型
            max_context: 最大上下文消息数（包括 system 消息），建议 10-20 条
            context: 可选的 AgentContext；缺省时通过工厂函数自动创建
            cache_strategy: "single_message"（默认，向后兼容）或 "multi_message"
        """
        cfg = provider_manager.get_api_config("main_llm")
        self.api_key = api_key or cfg.get("api_key", "")
        self.model = model or cfg.get("model", "")
        self.base_url = url or cfg.get("url", "")
        self._provider: Optional[OpenAICompatibleProvider] = None
        self._init_provider()

        self.max_context = max_context
        self.cache_strategy = cache_strategy
        self._lock = threading.RLock()

        if context is not None:
            self.context = context
        else:
            self.context = create_chat_context(
                character_prompt=get_character_prompt(),
                dialogue_examples=get_dialogue_examples(),
                persona_additional_prompt=config_loader.persona.additional_prompt,
            )

        # Apply context.yaml overrides (optional, fail gracefully)
        try:
            from .context.config import load_context_config
            ctx_config = load_context_config()
            agent_cfg = ctx_config.get_agent_config("chat")
            if agent_cfg is not None:
                agent_cfg.apply_to(self.context)
                if agent_cfg.cache_strategy:
                    self.cache_strategy = agent_cfg.cache_strategy
        except Exception:
            pass

        # Add dynamic plan section that injects today's schedule
        self._add_plan_section()

        # Initialize RAG knowledge base flag
        self._rag_enabled = False
        self._rag_injected = False
        try:
            from ..config.loader import config_loader
            if config_loader.knowledge.enabled and config_loader.knowledge.inject_into_chat:
                self._rag_enabled = True
        except Exception:
            pass

        # Build initial messages from context
        self.messages = list(self.context.build_messages_head(self.cache_strategy))

        # 监听配置变更以热更新
        bus.on("config_reloaded", self._on_config_reloaded)

    def _init_provider(self):
        """根据当前 api_key/base_url 初始化 OpenAICompatibleProvider。"""
        if self.api_key and self.base_url:
            self._provider = OpenAICompatibleProvider(
                name="chatllm",
                api_key=self.api_key,
                base_url=self.base_url,
                default_model=self.model,
            )
        else:
            self._provider = None

    def refresh_context(self):
        """Rebuild the system message(s) from context (call after config changes)."""
        with self._lock:
            new_head = self.context.build_messages_head(self.cache_strategy)
            # Replace all leading system messages from the old context
            cut = 0
            for m in self.messages:
                if m.get("role") == "system":
                    cut += 1
                else:
                    break
            self.messages = new_head + self.messages[cut:]

    def _add_plan_section(self):
        """Add a dynamic PromptSection that injects today's plan into the system prompt."""
        def _get_plan_content():
            from . import get_planllm
            try:
                planllm = get_planllm()
                planllm.ensure_today_plan()
                plan_text = planllm.get_today_plan_display()
                return "\n\n## 今日日程\n" + plan_text
            except Exception:
                return ""

        self.context.add_section(PromptSection(
            name="today_plan",
            content="",
            cacheable=False,
            order=100,
            _content_provider=_get_plan_content,
        ))

    def refresh_plan(self):
        """Refresh the plan section content and rebuild system messages."""
        self._add_plan_section()
        self.refresh_context()

    def _on_config_reloaded(self):
        """配置重载后热更新 API 客户端和角色上下文。"""
        with self._lock:
            cfg = provider_manager.get_api_config("main_llm")
            api_key = cfg.get("api_key", "")
            base_url = cfg.get("url", "")
            model = cfg.get("model", "")
            if api_key and base_url:
                self.api_key = api_key
                self.base_url = base_url
            if model:
                self.model = model
            self._init_provider()
            # 重建角色上下文
            self.context = create_chat_context(
                character_prompt=get_character_prompt(),
                dialogue_examples=get_dialogue_examples(),
                persona_additional_prompt=config_loader.persona.additional_prompt,
            )
            self._add_plan_section()
            self.refresh_context()
            logger.info("ChatLLM: 配置已热更新")

    def chat(self, user_input):
        """
        发送消息并获取回复，自动维护上下文
        """
        # RAG 检索：在 system 消息之后、conversation 之前注入知识库上下文
        rag_system_msg = None
        if self._rag_enabled:
            try:
                from ..rag.knowledge_manager import knowledge_manager
                rag_text = knowledge_manager.retrieve(user_input)
                if rag_text:
                    rag_system_msg = {"role": "system", "content": rag_text}
            except Exception:
                pass

        # 挂起用户消息并获取当前上下文快照（短持有锁）
        with self._lock:
            if rag_system_msg:
                # 插入在所有 system 消息之后、对话历史之前
                cut = 0
                for m in self.messages:
                    if m.get("role") == "system":
                        cut += 1
                    else:
                        break
                self.messages.insert(cut, rag_system_msg)
                self._rag_injected = True
            else:
                self._rag_injected = False

            self.messages.append({"role": "user", "content": user_input})
            self._trim_context()
            messages_snapshot = list(self.messages)

        # 在锁外执行 LLM API 调用（可能耗时 1-10s）
        try:
            response = self._provider.chat(
                messages=messages_snapshot,
                model=self.model,
            )
        except Exception as e:
            logger.error("ChatLLM API 调用失败: %s", e)
            # API 失败时回滚已追加的 user 消息，避免孤立 user 轮次
            with self._lock:
                if self.messages and self.messages[-1].get("role") == "user":
                    self.messages.pop()
            raise

        if response is None:
            logger.error("ChatLLM API 返回空响应")
            with self._lock:
                if self.messages and self.messages[-1].get("role") == "user":
                    self.messages.pop()
            raise RuntimeError("ChatLLM API 返回空响应")

        assistant_reply = response

        # 重新获取锁，追加助手回复
        with self._lock:
            # 清理注入的 RAG 系统消息
            if self._rag_injected:
                self.messages = [
                    m for m in self.messages
                    if not (isinstance(m.get("content"), str) and "## 知识库参考信息" in m["content"])
                ]
            self.messages.append({"role": "assistant", "content": assistant_reply})

        return assistant_reply

    def _trim_context(self):
        """修剪上下文，确保不超过 max_context 限制。
        始终保留所有 system 消息，从非 system 消息中成对删除最早的用户-助手回合。
        """
        while len(self.messages) > self.max_context:
            system_msgs = [m for m in self.messages if m.get("role") == "system"]
            non_system = [m for m in self.messages if m.get("role") != "system"]

            if len(non_system) >= 2:
                # 删除最早的一对非 system 消息
                non_system = non_system[2:]
            elif len(non_system) == 1:
                # 只剩一条，也删除
                non_system = []
            else:
                # 没有任何非 system 消息可删，强制截断到只剩 system 消息
                logger.warning("上下文超过限制但无可删除的非系统消息，强制保留 system 消息")
                self.messages = system_msgs
                return

            self.messages = system_msgs + non_system

    def clear_history(self):
        """清空对话历史，只保留 system 消息"""
        with self._lock:
            self.messages = list(self.context.build_messages_head(self.cache_strategy))

    def get_history(self):
        """获取当前对话历史"""
        with self._lock:
            return self.messages.copy()

    def set_history(self, messages: list):
        """设置对话历史（供外部如 WebUI 切换会话时使用）"""
        with self._lock:
            if not messages:
                self.clear_history()
                return
            # Rebuild system head, then append conversation messages
            system_head = self.context.build_messages_head(self.cache_strategy)
            conv_msgs = [m for m in messages if m.get("role") != "system"]
            self.messages = system_head + conv_msgs
            self._trim_context()





if __name__ == "__main__":
    pass
