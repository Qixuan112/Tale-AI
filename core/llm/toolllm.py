from typing import Optional

from ..tools.registry import (
    get_tools_list, format_tools_for_chatllm, build_fc_prompt, get_registry,
)
from ..utils import get_logger
from .context import AgentContext, create_tool_context
from .provider import OpenAICompatibleProvider, provider_manager

logger = get_logger(__name__)


# 兼容旧代码：从注册表转发
AVAILABLE_TOOLS = [
    {"name": t.name, "description": t.description,
     "parameters": {p.name: p.description for p in t.parameters}}
    for t in __import__('core.tools.registry', fromlist=['get_registry']).get_registry().list_tools()
]


# ToolLLM 的 Function Calling 提示词（JSON 格式）— 保留向后兼容
TOOL_FC_PROMPT = build_fc_prompt()


class ToolLLM:
    """
    工具型 AI：根据 action 输出 Function Calling JSON
    """
    def __init__(self, api_key=None, model=None, url=None,
                 context: Optional[AgentContext] = None,
                 cache_strategy: str = "single_message"):
        cfg = provider_manager.get_api_config("tool_llm")
        self.api_key = api_key or cfg.get("api_key", "")
        self.model = model or cfg.get("model", "")
        self.base_url = url or cfg.get("url", "")
        self._provider: Optional[OpenAICompatibleProvider] = None
        self._init_provider()
        self.cache_strategy = cache_strategy

        if context is not None:
            self.context = context
        else:
            self.context = create_tool_context(
                tools_text=get_registry().get_tools_list_text(),
            )

        # Apply context.yaml overrides (optional, fail gracefully)
        try:
            from .context.config import load_context_config
            ctx_config = load_context_config()
            agent_cfg = ctx_config.get_agent_config("tool")
            if agent_cfg is not None:
                agent_cfg.apply_to(self.context)
                if agent_cfg.cache_strategy:
                    self.cache_strategy = agent_cfg.cache_strategy
        except Exception:
            pass

    def _init_provider(self):
        """根据当前 api_key/base_url 初始化 OpenAICompatibleProvider。"""
        if self.api_key and self.base_url:
            self._provider = OpenAICompatibleProvider(
                name="toolllm",
                api_key=self.api_key,
                base_url=self.base_url,
                default_model=self.model,
                timeout=30,
            )
        else:
            self._provider = None

    def generate_fc(self, action):
        """
        根据动作指令生成 Function Calling JSON

        Args:
            action: 动作指令，如"搜索今天黄金价格"

        Returns:
            Function Calling JSON 字符串
        """
        try:
            messages = self.context.build_messages_head(self.cache_strategy) + [
                {"role": "user", "content": f"动作指令：{action}"},
            ]
            if self._provider is None:
                raise RuntimeError("ToolLLM provider 未初始化")
            response = self._provider.chat(
                messages=messages,
                model=self.model,
            )
            return response or ""
        except Exception as e:
            logger.error("ToolLLM generate_fc 失败: %s", e)
            raise

    def query_tools(self) -> str:
        """
        查询可用工具列表，用 <chatllm> 标签格式返回

        Returns:
            包含 <chatllm> 标签的工具列表
        """
        return format_tools_for_chatllm()

    def rebuild_tool_definitions(self):
        """更新 tool_definitions 段内容（工具注册表变更后调用）。"""
        tools_text = get_registry().get_tools_list_text()
        self.context.set_section_content("tool_definitions", tools_text)
        # Also rebuild the fc_format_template which embeds the tools list
        fc_intro = (
            "你是 \"ToolLLM\"，工具调用专家。你的任务是分析用户的动作指令，"
            "输出标准化的 Function Calling JSON。\n\n" + tools_text
        )
        from ..config.prompt import FC_FORMAT_TEMPLATE
        self.context.set_section_content(
            "fc_format_template",
            fc_intro + FC_FORMAT_TEMPLATE.strip(),
        )


# 全局实例（懒加载）
toolllm: Optional[ToolLLM] = None


def get_toolllm() -> ToolLLM:
    """获取全局 ToolLLM 实例（懒初始化）"""
    global toolllm
    if toolllm is None:
        toolllm = ToolLLM()
    return toolllm
