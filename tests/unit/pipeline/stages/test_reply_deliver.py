"""
Unit tests for ReplyDeliverStage (TO BE IMPLEMENTED)

Tests message delivery through adapter bridge.

Expected behavior based on core/main.py _handle_respond_message:
- Order: 800
- Sends parsed messages through adapter_bridge
- Handles both single and batch message sending
- Applies typing delay simulation between messages
- Handles send failures and stores failed files
- Processes cross-session message sends (session_send tags)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.pipeline.context import PipelineContext
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType


@pytest.fixture
def mock_adapter_bridge():
    """Mock AdapterEventBridge"""
    bridge = AsyncMock()
    bridge.send_message = AsyncMock(return_value=True)
    return bridge


@pytest.fixture
def mock_bridge_state():
    """Mock BridgeState for cross-session messages"""
    bridge = AsyncMock()
    bridge.send = AsyncMock(return_value={"success": True})
    return bridge


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


class TestReplyDeliverStage:
    """Test ReplyDeliverStage"""

    def test_stage_initialization(self, mock_adapter_bridge):
        """Should initialize with order 800 and name 'reply_deliver'"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        stage = ReplyDeliverStage(mock_adapter_bridge)
        assert stage.order == 800
        assert stage.name == "reply_deliver"

    @pytest.mark.asyncio
    async def test_process_sends_single_message(self, mock_adapter_bridge, mock_processed):
        """Should send single message through adapter bridge"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        msg = Message()
        msg.add_element(Text("Hello user"))
        ctx.parsed = {"messages": [msg]}
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        mock_adapter_bridge.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_sends_multiple_messages(self, mock_adapter_bridge, mock_processed):
        """Should send multiple messages with delay"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        msg1, msg2, msg3 = Message(), Message(), Message()
        msg1.add_element(Text("First"))
        msg2.add_element(Text("Second"))
        msg3.add_element(Text("Third"))
        ctx.parsed = {"messages": [msg1, msg2, msg3]}
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        assert mock_adapter_bridge.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_process_applies_typing_delay(self, mock_adapter_bridge, mock_processed):
        """Should apply typing delay between messages"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text
        import time

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        msg1, msg2 = Message(), Message()
        msg1.add_element(Text("First"))
        msg2.add_element(Text("Second"))
        ctx.parsed = {"messages": [msg1, msg2]}
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        start = time.time()
        await stage.process(ctx)
        elapsed = time.time() - start

        # Should have some delay between messages
        assert elapsed > 0.1  # At least some delay

    @pytest.mark.asyncio
    async def test_process_skips_when_skip_reply_flag(self, mock_adapter_bridge, mock_processed):
        """Should skip sending when ctx.skip_reply is True"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        ctx.skip_reply = True
        msg = Message()
        msg.add_element(Text("Hello"))
        ctx.parsed = {"messages": [msg]}

        await stage.process(ctx)

        mock_adapter_bridge.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_handles_send_failure(self, mock_adapter_bridge, mock_processed):
        """Should handle message send failures"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        mock_adapter_bridge.send_message.side_effect = RuntimeError("Send failed")
        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        msg = Message()
        msg.add_element(Text("Hello"))
        ctx.parsed = {"messages": [msg]}
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        # Should not crash
        await stage.process(ctx)

        # Error should be logged or stored

    @pytest.mark.asyncio
    async def test_process_handles_parse_error_fallback(self, mock_adapter_bridge, mock_processed):
        """Should send raw chatllm_reply when parse_error is True"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        ctx.parsed = {"parse_error": True, "messages": []}
        ctx.chatllm_reply = "Raw text reply"
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        # Should send raw reply
        call_args = mock_adapter_bridge.send_message.call_args
        assert "Raw text reply" in str(call_args)

    @pytest.mark.asyncio
    async def test_process_sends_to_group(self, mock_adapter_bridge, mock_processed):
        """Should send to group when is_group is True"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        msg = Message()
        msg.add_element(Text("Hello group"))
        ctx.parsed = {"messages": [msg]}
        ctx.is_group = True
        ctx.target_id = "group456"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        call_kwargs = mock_adapter_bridge.send_message.call_args[1]
        assert call_kwargs["is_group"] is True

    @pytest.mark.asyncio
    async def test_process_includes_reply_to(self, mock_adapter_bridge, mock_processed):
        """Should include reply_to message ID"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        msg = Message()
        msg.add_element(Text("Reply"))
        ctx.parsed = {"messages": [msg]}
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        call_kwargs = mock_adapter_bridge.send_message.call_args[1]
        # reply_to should be None when not explicitly set in Message
        assert "reply_to" in call_kwargs

    @pytest.mark.asyncio
    async def test_process_sends_cross_session_messages(self, mock_adapter_bridge, mock_bridge_state, mock_processed):
        """Should send cross-session messages from session_sends"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        mock_bridge_state.send = AsyncMock(return_value="msg_id_123")
        mock_bridge_state.ack = AsyncMock()

        stage = ReplyDeliverStage(
            adapter_bridge=mock_adapter_bridge,
            bridge=mock_bridge_state
        )
        ctx = PipelineContext(processed=mock_processed)
        msg = Message()
        msg.add_element(Text("OK"))
        ctx.parsed = {
            "messages": [msg],
            "session_sends": [
                {"target": "qq:dm:987654321", "text": "Cross-session message"}
            ]
        }
        ctx.sid = "qq:dm:user123"
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        mock_bridge_state.send.assert_called_once_with(
            "qq:dm:user123",
            "qq:dm:987654321",
            "Cross-session message"
        )

    @pytest.mark.asyncio
    async def test_process_respects_max_split_count(self, mock_adapter_bridge, mock_processed):
        """Should limit number of messages sent to MAX_SPLIT_COUNT"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        stage = ReplyDeliverStage(mock_adapter_bridge, max_messages=3)
        ctx = PipelineContext(processed=mock_processed)
        messages = []
        for i in range(6):
            msg = Message()
            msg.add_element(Text(str(i + 1)))
            messages.append(msg)
        ctx.parsed = {"messages": messages}
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        # Should only send first 3 messages
        assert mock_adapter_bridge.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_process_stores_failed_files(self, mock_adapter_bridge, mock_processed):
        """Should store failed file uploads in ctx.failed_files"""
        from core.pipeline.stages.reply_deliver import ReplyDeliverStage
        from core.message import Message, Text

        # Create a mock result object with failed_files attribute
        mock_result = MagicMock()
        mock_result.failed_files = ["file1.jpg", "file2.pdf"]
        mock_result.__bool__ = lambda self: True
        mock_adapter_bridge.send_message = AsyncMock(return_value=mock_result)

        stage = ReplyDeliverStage(mock_adapter_bridge)
        ctx = PipelineContext(processed=mock_processed)
        msg = Message()
        msg.add_element(Text("Hello with files"))
        ctx.parsed = {"messages": [msg]}
        ctx.target_id = "user123"
        ctx.platform_name = "qq"

        await stage.process(ctx)

        assert "file1.jpg" in ctx.failed_files
        assert "file2.pdf" in ctx.failed_files
