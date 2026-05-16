from openai import OpenAI
from ..config import provide
from ..tools.registry import get_tools_list, format_tools_for_chatllm, build_fc_prompt
from ..utils import get_logger
import json

logger = get_logger(__name__)


# 兼容旧代码：从注册表转发
AVAILABLE_TOOLS = [
    {"name": t.name, "description": t.description,
     "parameters": {p.name: p.description for p in t.parameters}}
    for t in __import__('core.tools.registry', fromlist=['get_registry']).get_registry().list_tools()
]


# ToolLLM 的 Function Calling 提示词（JSON 格式）
TOOL_FC_PROMPT = build_fc_prompt()


class ToolLLM:
    """
    工具型 AI：根据 action 输出 Function Calling JSON
    """
    def __init__(self, api_key=None, model=None, url=None):
        self.client = OpenAI(
            api_key=api_key or provide.TOOL_API_KEY,
            base_url=url or provide.TOOL_URL,
        )
        self.model = model or provide.TOOL_MODEL

    def generate_fc(self, action):
        """
        根据动作指令生成 Function Calling JSON

        Args:
            action: 动作指令，如"搜索今天黄金价格"

        Returns:
            Function Calling JSON 字符串
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": TOOL_FC_PROMPT},
                    {"role": "user", "content": f"动作指令：{action}"},
                ],
            )
            return response.choices[0].message.content
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


# 创建全局实例
toolllm = ToolLLM()
