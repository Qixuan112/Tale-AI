"""MessageParseStage - XML 消息解析阶段

Order: 600
解析 ChatLLM 的 XML 回复，处理三种场景：
1. skip_reply: AI 主动不回复（<msg></msg>）
2. parse_error: XML 解析失败，直接发送原始回复
3. non-xml: 纯文本回复（无消息且无工具调用），直接发送
"""

from core.pipeline.stage import PipelineStage
from core.parse_xml import parse_xml_msg
from core.message import Message, Text
from core.utils import get_logger

logger = get_logger(__name__)


class MessageParseStage(PipelineStage):
    """消息解析阶段 - 解析 ChatLLM 的 XML 回复"""

    def __init__(self):
        super().__init__(order=600, name="message_parse")

    async def process(self, ctx) -> None:
        """解析 ctx.chatllm_reply 并设置 ctx.parsed 和 ctx.messages_to_send

        处理逻辑：
        1. 解析 XML 回复
        2. 检测 skip_reply（AI 主动不回复）
        3. 检测 parse_error（XML 解析失败，发送原始文本）
        4. 检测 non-xml（无消息且无工具调用，发送原始文本）
        5. 正常情况：设置 messages_to_send
        """
        # 处理 None 或空回复
        if ctx.chatllm_reply is None or ctx.chatllm_reply == "":
            logger.warning("chatllm_reply 为空，设置默认解析结果")
            ctx.parsed = {
                "messages": [],
                "action": None,
                "actions": [],
                "plan": None,
                "skip_reply": False,
                "session_sends": [],
            }
            return

        # 解析 XML
        parsed = parse_xml_msg(ctx.chatllm_reply)
        ctx.parsed = parsed

        # 场景1: AI 主动不回复（<msg></msg>）
        if parsed.get("skip_reply") and not parsed.get("messages") and not self._has_tool_content(parsed):
            logger.info("AI 选择不回复消息 (skip_reply)")
            ctx.skip_reply = True
            return

        # 场景2: XML 解析失败，直接发送原始回复
        if parsed.get("parse_error"):
            logger.warning("XML 解析失败，使用原始回复")
            # 将原始文本包装成 Message 对象
            msg = Message()
            msg.add_element(Text(ctx.chatllm_reply))
            ctx.messages_to_send = [msg]
            return

        # 场景3: 非 XML 回复（无消息且无工具调用），直接发送原始文本
        first_messages = parsed.get("messages", [])
        needs_follow_up = self._has_tool_content(parsed)

        if not first_messages and not needs_follow_up:
            logger.warning("ChatLLM 返回了非 XML 格式回复，直接作为纯文本发送")
            # 将原始文本包装成 Message 对象
            msg = Message()
            msg.add_element(Text(ctx.chatllm_reply))
            ctx.messages_to_send = [msg]
            return

        # 场景4: 正常情况，设置消息列表
        ctx.messages_to_send = first_messages

    def _has_tool_content(self, parsed: dict) -> bool:
        """检查解析结果是否包含工具调用相关内容

        检查项：
        - actions/action: <act> 标签
        - plan: <plan> 标签
        """
        if not parsed:
            return False

        # 检查 <act> 标签
        if parsed.get("actions") or parsed.get("action"):
            return True

        # 检查 <plan> 标签
        if parsed.get("plan"):
            return True

        return False
