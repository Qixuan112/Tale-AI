"""
Unit tests for MessageParseStage

Tests XML message parsing from LLM reply.

Expected behavior based on core/main.py _handle_respond_message:
- Order: 600
- Parses ctx.chatllm_reply using parse_xml_msg()
- Stores parsed result in ctx.parsed (dict with keys: messages, skip_reply, parse_error, session_sends, etc.)
- Handles parse errors gracefully
- Sets ctx.skip_reply flag if AI returns empty <msg></msg>
"""
import pytest
from unittest.mock import MagicMock, patch
from core.pipeline.context import PipelineContext
from core.pipeline.stages.message_parse import MessageParseStage
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType
from core.message import Message, Text


@pytest.fixture
def mock_processed():
    """Create a basic ProcessedMessage"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        sender_id="user123",
        sender_name="TestUser",
        text="Hello",
        message_id="msg001",
        group_id=None,
        group_name=None,
        at_targets=[],
        reply_to=None,
        reply_text=None,
        images=[],
        files=[],
        voices=[],
        faces=[],
        stickers=[],
        videos=[],
        is_group_message=False,
        reason="wake_word",
        decision=None
    )


class TestMessageParseStage:
    """Test MessageParseStage"""

    def test_stage_initialization(self):
        """Should initialize with order 600 and name 'message_parse'"""
        stage = MessageParseStage()
        assert stage.order == 600
        assert stage.name == "message_parse"

    @pytest.mark.asyncio
    async def test_process_parses_xml_reply(self, mock_processed):
        """Should parse XML from chatllm_reply"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg><text>Hello user</text></msg>"

        await stage.process(ctx)

        assert ctx.parsed is not None
        assert "messages" in ctx.parsed
        assert len(ctx.parsed["messages"]) == 1
        # Messages are Message objects, not strings
        assert isinstance(ctx.parsed["messages"][0], Message)
        assert len(ctx.messages_to_send) == 1

    @pytest.mark.asyncio
    async def test_process_handles_skip_reply(self, mock_processed):
        """Should set skip_reply flag for empty <msg></msg>"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg></msg>"

        await stage.process(ctx)

        assert ctx.parsed.get("skip_reply") is True
        assert ctx.skip_reply is True

    @pytest.mark.asyncio
    async def test_process_handles_parse_error(self, mock_processed):
        """Should mark parse_error for invalid XML"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg><text>Unclosed tag"

        await stage.process(ctx)

        assert ctx.parsed is not None
        assert ctx.parsed.get("parse_error") is not None
        # Should wrap original text in Message object
        assert len(ctx.messages_to_send) == 1
        assert isinstance(ctx.messages_to_send[0], Message)

    @pytest.mark.asyncio
    async def test_process_parses_multiple_messages(self, mock_processed):
        """Should parse multiple <msg> tags"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg><text>First</text></msg><msg><text>Second</text></msg>"

        await stage.process(ctx)

        assert len(ctx.parsed["messages"]) == 2
        assert isinstance(ctx.parsed["messages"][0], Message)
        assert isinstance(ctx.parsed["messages"][1], Message)
        assert len(ctx.messages_to_send) == 2

    @pytest.mark.asyncio
    async def test_process_parses_tool_tags(self, mock_processed):
        """Should parse <act> tags for tool calls"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg><text>Searching...</text></msg><act>browser_search</act>"

        await stage.process(ctx)

        # Should have actions in parsed result
        assert "actions" in ctx.parsed or "action" in ctx.parsed
        if "actions" in ctx.parsed:
            assert len(ctx.parsed["actions"]) > 0
        if "action" in ctx.parsed:
            assert ctx.parsed["action"] is not None

    @pytest.mark.asyncio
    async def test_process_parses_session_send_tags(self, mock_processed):
        """Should parse <session_send> tags for cross-session messages"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = '<msg><text>OK</text></msg><session_send>qq:dm:other|Message</session_send>'

        await stage.process(ctx)

        assert "session_sends" in ctx.parsed
        assert len(ctx.parsed["session_sends"]) == 1
        assert ctx.parsed["session_sends"][0]["target"] == "qq:dm:other"
        assert ctx.parsed["session_sends"][0]["text"] == "Message"

    @pytest.mark.asyncio
    async def test_process_parses_act_tags(self, mock_processed):
        """Should parse <act> tags for actions"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg><text>Done</text></msg><act>action_name</act>"

        await stage.process(ctx)

        assert "actions" in ctx.parsed or "action" in ctx.parsed
        if "actions" in ctx.parsed:
            assert len(ctx.parsed["actions"]) > 0
        if "action" in ctx.parsed:
            assert ctx.parsed["action"] is not None

    @pytest.mark.asyncio
    async def test_process_with_none_reply(self, mock_processed):
        """Should handle None chatllm_reply"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = None

        await stage.process(ctx)

        # Should set default empty parsed
        assert ctx.parsed is not None
        assert ctx.parsed["messages"] == []
        assert ctx.parsed["skip_reply"] is False

    @pytest.mark.asyncio
    async def test_process_with_empty_reply(self, mock_processed):
        """Should handle empty string reply"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = ""

        await stage.process(ctx)

        assert ctx.parsed is not None
        assert ctx.parsed["messages"] == []
        assert ctx.parsed["skip_reply"] is False

    @pytest.mark.asyncio
    async def test_process_plain_text_fallback(self, mock_processed):
        """Should handle plain text (non-XML) replies"""
        stage = MessageParseStage()
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "Just plain text without XML"

        await stage.process(ctx)

        # Plain text without XML tags returns empty messages, triggering non-xml fallback
        # Should wrap text in Message
        assert len(ctx.messages_to_send) == 1
        assert isinstance(ctx.messages_to_send[0], Message)
