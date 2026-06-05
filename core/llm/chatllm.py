from typing import Optional

from openai import OpenAI
from ..bus import bus
from ..config import MAX_CONTEXT
from ..config.provide import get_character_prompt, get_dialogue_examples, config_loader
from ..utils import get_logger
from .context import AgentContext, create_chat_context

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
        self.client = OpenAI(api_key=api_key, base_url=url)
        self.model = model
        self.max_context = max_context
        self.cache_strategy = cache_strategy

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

        # Build initial messages from context
        self.messages = list(self.context.build_messages_head(self.cache_strategy))

        # 监听配置变更以热更新
        bus.on("config_reloaded", self._on_config_reloaded)

    def refresh_context(self):
        """Rebuild the system message(s) from context (call after config changes)."""
        new_head = self.context.build_messages_head(self.cache_strategy)
        # Replace all leading system messages from the old context
        cut = 0
        for m in self.messages:
            if m.get("role") == "system":
                cut += 1
            else:
                break
        self.messages = new_head + self.messages[cut:]

    def _on_config_reloaded(self):
        """配置重载后热更新 API 客户端和角色上下文。"""
        cfg = config_loader.chat_api
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("url", "")
        model = cfg.get("model", "")
        if api_key and base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        if model:
            self.model = model
        # 重建角色上下文
        self.context = create_chat_context(
            character_prompt=get_character_prompt(),
            dialogue_examples=get_dialogue_examples(),
            persona_additional_prompt=config_loader.persona.additional_prompt,
        )
        self.refresh_context()
        logger.info("ChatLLM: 配置已热更新")

    def chat(self, user_input):
        """
        发送消息并获取回复，自动维护上下文
        """
        self.messages.append({"role": "user", "content": user_input})
        self._trim_context()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages
            )
        except Exception as e:
            logger.error("ChatLLM API 调用失败: %s", e)
            raise

        assistant_reply = response.choices[0].message.content
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
        self.messages = list(self.context.build_messages_head(self.cache_strategy))

    def get_history(self):
        """获取当前对话历史"""
        return self.messages.copy()

    def set_history(self, messages: list):
        """设置对话历史（供外部如 WebUI 切换会话时使用）"""
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
