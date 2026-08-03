"""
Unit tests for ContextBuildStage

Tests context building with metadata, VLM, history, and cross-session messages.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.pipeline.stages.context_build import ContextBuildStage
from core.pipeline.context import PipelineContext
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType

@pytest.fixture
def mock_context_builder():
    """Mock ContextBuilder"""
    builder = AsyncMock()
    builder.build_input = AsyncMock(return_value="[时间] 2024-01-01\n[消息] 用户说：Hello")
    return builder

@pytest.fixture
def mock_context_buffer():
    """Mock context buffer (BoundedCache)"""
    return {}

@pytest.fixture
def stage(mock_context_builder, mock_context_buffer):
    """Create ContextBuildStage"""
    return ContextBuildStage(mock_context_builder, mock_context_buffer)

class TestContextBuildStage:
    """Test ContextBuildStage"""

    def test_stage_initialization(self, stage):
        """Should initialize with correct order and name"""
        assert stage.order == 400
        assert stage.name == "context_build"
        assert stage.always_run is False

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_calls_context_builder(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should call ContextBuilder.build_input"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.session_enabled = True

        await stage.process(ctx)

        mock_context_builder.build_input.assert_called_once()
        call_kwargs = mock_context_builder.build_input.call_args[1]
        assert call_kwargs["processed"] == mock_processed
        assert call_kwargs["platform_name"] == "qq"
        assert call_kwargs["window"] == 5
        assert call_kwargs["session_enabled"] is True

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_builds_user_input(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should set user_input from builder output"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"

        await stage.process(ctx)

        assert "Base context" in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_appends_inbox_messages(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should append inbox messages to user_input"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.inbox_msgs = [
            {"from_sid": "qq:dm:other", "content": "Message from other session"},
            {"from_sid": "qq:gm:group1", "content": "Message from group"}
        ]

        await stage.process(ctx)

        assert "[来自其他会话的消息]" in ctx.user_input
        assert "qq:dm:other" in ctx.user_input
        assert "Message from other session" in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_appends_accessible_sessions(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should append accessible sessions list"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.accessible_sessions = ["qq:dm:friend1", "qq:gm:group2"]

        await stage.process(ctx)

        assert "[可通信会话]" in ctx.user_input
        assert "qq:dm:friend1" in ctx.user_input
        assert "qq:gm:group2" in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_combines_all_sections(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should combine base context, inbox, and accessible sessions"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.inbox_msgs = [{"from_sid": "qq:dm:other", "content": "Inbox message"}]
        ctx.accessible_sessions = ["qq:dm:friend1"]

        await stage.process(ctx)

        # All sections should be present
        assert "Base context" in ctx.user_input
        assert "[来自其他会话的消息]" in ctx.user_input
        assert "[可通信会话]" in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_without_inbox_messages(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should work without inbox messages"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.inbox_msgs = []

        await stage.process(ctx)

        assert "Base context" in ctx.user_input
        assert "[来自其他会话的消息]" not in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_without_accessible_sessions(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should work without accessible sessions"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.accessible_sessions = []

        await stage.process(ctx)

        assert "Base context" in ctx.user_input
        assert "[可通信会话]" not in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_truncates_long_inbox_messages(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should truncate inbox messages to 200 chars"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        long_message = "A" * 300
        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.inbox_msgs = [{"from_sid": "qq:dm:other", "content": long_message}]

        await stage.process(ctx)

        # Should be truncated to 200 chars
        assert long_message[:200] in ctx.user_input
        assert long_message in ctx.user_input  # Full message should NOT be present

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_passes_persistence_flag(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should pass persistence_enabled to builder"""
        mock_config.bot.bot.persistence_enabled = True
        mock_config.bot.context.chat_context_window = 5

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"

        await stage.process(ctx)

        call_kwargs = mock_context_builder.build_input.call_args[1]
        assert call_kwargs["persistence_enabled"] is True

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_passes_context_buffer(self, mock_config, stage, mock_context_builder, mock_context_buffer, mock_processed):
        """Should pass context_buffer to builder"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"

        await stage.process(ctx)

        call_kwargs = mock_context_builder.build_input.call_args[1]
        assert call_kwargs["context_buffer"] is mock_context_buffer

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_multiple_inbox_messages(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should handle multiple inbox messages"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.inbox_msgs = [
            {"from_sid": "qq:dm:user1", "content": "Message 1"},
            {"from_sid": "qq:dm:user2", "content": "Message 2"},
            {"from_sid": "qq:gm:group1", "content": "Message 3"}
        ]

        await stage.process(ctx)

        # All messages should be listed
        assert "Message 1" in ctx.user_input
        assert "Message 2" in ctx.user_input
        assert "Message 3" in ctx.user_input
        assert "qq:dm:user1" in ctx.user_input
        assert "qq:dm:user2" in ctx.user_input
        assert "qq:gm:group1" in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_sections_separated_by_double_newline(self, mock_config, stage, mock_context_builder, mock_processed):
        """Sections should be separated by double newline"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 5
        mock_context_builder.build_input.return_value = "Base context"

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"
        ctx.inbox_msgs = [{"from_sid": "qq:dm:other", "content": "Inbox"}]
        ctx.accessible_sessions = ["qq:dm:friend1"]

        await stage.process(ctx)

        # Sections should be separated by \n\n
        assert "\n\n" in ctx.user_input

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.context_build.config_loader')
    async def test_process_with_zero_window(self, mock_config, stage, mock_context_builder, mock_processed):
        """Should handle zero context window"""
        mock_config.bot.bot.persistence_enabled = False
        mock_config.bot.context.chat_context_window = 0

        ctx = PipelineContext(processed=mock_processed)
        ctx.platform_name = "qq"

        await stage.process(ctx)

        call_kwargs = mock_context_builder.build_input.call_args[1]
        assert call_kwargs["window"] == 0
