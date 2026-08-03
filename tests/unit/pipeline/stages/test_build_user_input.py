"""
Unit tests for BuildUserInputStage

Tests user input formatting and metadata extraction.
"""
import pytest
from unittest.mock import MagicMock
from core.pipeline.stages.build_user_input import BuildUserInputStage
from core.pipeline.context import PipelineContext
from core.adapter.message_processor import ProcessedMessage, ResponseDecision
from core.adapter.event import PlatformType, EventType

@pytest.fixture
def stage():
    """Create BuildUserInputStage"""
    return BuildUserInputStage()

class TestBuildUserInputStage:
    """Test BuildUserInputStage"""

    def test_stage_initialization(self, stage):
        """Should initialize with correct order and name"""
        assert stage.order == 100
        assert stage.name == "build_user_input"
        assert stage.always_run is False

    @pytest.mark.asyncio
    async def test_process_private_message(self, stage, mock_processed):
        """Should process private message correctly"""
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert ctx.platform_name == "qq"
        assert ctx.is_group is False
        assert ctx.target_id == "user123"
        assert ctx.user_text == "Hello world"
        assert ctx.persist_content == "Hello world"

    @pytest.mark.asyncio
    async def test_process_group_message(self, stage, mock_processed):
        """Should process group message correctly"""
        mock_processed.group_id = "group456"
        mock_processed.group_name = "Test Group"
        mock_processed.is_group_message = True
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert ctx.platform_name == "qq"
        assert ctx.is_group is True
        assert ctx.target_id == "group456"

    @pytest.mark.asyncio
    async def test_process_with_at_targets(self, stage, mock_processed):
        """Should format At tags in user_text"""
        mock_processed.at_targets = ["bot123", "user456"]
        mock_processed.text = "Hello everyone"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert "[At bot123]" in ctx.user_text
        assert "[At user456]" in ctx.user_text
        assert "Hello everyone" in ctx.user_text

    @pytest.mark.asyncio
    async def test_process_with_reply(self, stage, mock_processed):
        """Should format Reply tag in user_text"""
        mock_processed.reply_to = "msg000"
        mock_processed.reply_text = "Original message"
        mock_processed.text = "Yes, agreed"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert "[回复: Original message]" in ctx.user_text
        assert "Yes, agreed" in ctx.user_text

    @pytest.mark.asyncio
    async def test_process_with_reply_no_text(self, stage, mock_processed):
        """Should use Reply ID when reply_text is None"""
        mock_processed.reply_to = "msg000"
        mock_processed.reply_text = None
        mock_processed.text = "Thanks"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert "[Reply msg000]" in ctx.user_text
        assert "Thanks" in ctx.user_text

    @pytest.mark.asyncio
    async def test_process_with_at_and_reply(self, stage, mock_processed):
        """Should format both At and Reply tags"""
        mock_processed.at_targets = ["user456"]
        mock_processed.reply_to = "msg000"
        mock_processed.reply_text = "Question"
        mock_processed.text = "Answer"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert "[At user456]" in ctx.user_text
        assert "[回复: Question]" in ctx.user_text
        assert "Answer" in ctx.user_text

    @pytest.mark.asyncio
    async def test_process_empty_text(self, stage, mock_processed):
        """Should handle empty text"""
        mock_processed.text = ""
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert ctx.user_text == ""
        assert ctx.persist_content == ""

    @pytest.mark.asyncio
    async def test_process_none_text(self, stage, mock_processed):
        """Should handle None text"""
        mock_processed.text = None
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert ctx.user_text == ""
        assert ctx.persist_content == ""

    @pytest.mark.asyncio
    async def test_process_platform_from_adapter_instance(self, stage, mock_processed):
        """Should use adapter_instance when platform is None"""
        mock_processed.platform = None
        ctx = PipelineContext(
            processed=mock_processed,
            adapter_instance="custom_adapter"
        )

        await stage.process(ctx)

        assert ctx.platform_name == "custom_adapter"

    @pytest.mark.asyncio
    async def test_process_platform_fallback_unknown(self, stage, mock_processed):
        """Should fallback to 'unknown' when no platform info"""
        mock_processed.platform = None
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert ctx.platform_name == "unknown"

    @pytest.mark.asyncio
    async def test_persist_content_matches_user_text(self, stage, mock_processed):
        """persist_content should match user_text for basic messages"""
        mock_processed.text = "Simple message"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert ctx.user_text == "Simple message"
        assert ctx.persist_content == "Simple message"

    @pytest.mark.asyncio
    async def test_persist_content_includes_tags(self, stage, mock_processed):
        """persist_content should include formatted tags"""
        mock_processed.at_targets = ["user456"]
        mock_processed.text = "Hello"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert ctx.persist_content == ctx.user_text
        assert "[At user456]" in ctx.persist_content

    @pytest.mark.asyncio
    async def test_multiple_at_targets(self, stage, mock_processed):
        """Should handle multiple at targets"""
        mock_processed.at_targets = ["user1", "user2", "user3"]
        mock_processed.text = "Meeting time"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        assert "[At user1]" in ctx.user_text
        assert "[At user2]" in ctx.user_text
        assert "[At user3]" in ctx.user_text
        assert "Meeting time" in ctx.user_text

    @pytest.mark.asyncio
    async def test_message_parts_spacing(self, stage, mock_processed):
        """Message parts should be space-separated"""
        mock_processed.at_targets = ["bot"]
        mock_processed.reply_to = "msg"
        mock_processed.reply_text = "Q"
        mock_processed.text = "A"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        parts = ctx.user_text.split()
        assert "[At" in parts[0]
        assert "[回复:" in ctx.user_text

    @pytest.mark.asyncio
    async def test_wechat_platform(self, stage):
        """Should handle WeChat platform"""
        processed = ProcessedMessage(
            platform=PlatformType.WECHAT,
            event_type=EventType.PRIVATE_MESSAGE,
            sender_id="wx123",
            sender_name="WXUser",
            text="WeChat message",
            message_id="wxmsg001",
            decision=ResponseDecision.RESPOND,
            reason="direct"
        )
        ctx = PipelineContext(processed=processed)

        await stage.process(ctx)

        assert ctx.platform_name == "wechat"
        assert ctx.user_text == "WeChat message"
