"""
Unit tests for SessionInitStage

Tests session initialization and inbox message consumption.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.pipeline.stages.session_init import SessionInitStage
from core.pipeline.context import PipelineContext
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType

@pytest.fixture
def mock_session_manager():
    """Mock SessionManager"""
    manager = MagicMock()
    session_obj = MagicMock()
    session_obj.enabled = True
    manager.get_or_create.return_value = session_obj
    return manager

@pytest.fixture
def mock_chat_llm():
    """Mock ChatLLM"""
    llm = MagicMock()
    llm.set_session = MagicMock()
    return llm

@pytest.fixture
def mock_bridge():
    """Mock BridgeState"""
    bridge = AsyncMock()
    bridge.consume = AsyncMock(return_value=[])
    bridge.list_accessible = MagicMock(return_value=[])
    return bridge

@pytest.fixture
def stage(mock_session_manager, mock_chat_llm, mock_bridge):
    """Create SessionInitStage"""
    return SessionInitStage(mock_session_manager, mock_chat_llm, mock_bridge)

class TestSessionInitStage:
    """Test SessionInitStage"""

    def test_stage_initialization(self, stage):
        """Should initialize with correct order and name"""
        assert stage.order == 300
        assert stage.name == "session_init"
        assert stage.always_run is False

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_private_message_sid(self, mock_config, stage, mock_processed):
        """Should construct sid for private message"""
        mock_config.bot.bot.persistence_enabled = True
        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        assert ctx.sid == "qq:dm:user123"

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_group_message_sid(self, mock_config, stage, mock_processed):
        """Should construct sid for group message"""
        mock_config.bot.bot.persistence_enabled = True
        mock_processed.group_id = "group456"
        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = True
        ctx.target_id = "group456"

        await stage.process(ctx)

        assert ctx.sid == "qq:gm:group456"

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_calls_session_manager(self, mock_config, stage, mock_session_manager, mock_processed):
        """Should call session manager when persistence enabled"""
        mock_config.bot.bot.persistence_enabled = True
        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        mock_session_manager.get_or_create.assert_called_once_with("qq:dm:user123")

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_sets_session_enabled(self, mock_config, stage, mock_session_manager, mock_processed):
        """Should set session_enabled from session object"""
        mock_config.bot.bot.persistence_enabled = True
        session_obj = MagicMock()
        session_obj.enabled = False
        mock_session_manager.get_or_create.return_value = session_obj

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        assert ctx.session_enabled is False

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_calls_set_session(self, mock_config, stage, mock_chat_llm, mock_processed):
        """Should call ChatLLM.set_session"""
        mock_config.bot.bot.persistence_enabled = True
        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        mock_chat_llm.set_session.assert_called_once_with("qq:dm:user123", load_history=True)

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_set_session_respects_enabled_flag(self, mock_config, stage, mock_chat_llm, mock_session_manager, mock_processed):
        """Should pass session_enabled to set_session"""
        mock_config.bot.bot.persistence_enabled = True
        session_obj = MagicMock()
        session_obj.enabled = False
        mock_session_manager.get_or_create.return_value = session_obj

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        mock_chat_llm.set_session.assert_called_once_with("qq:dm:user123", load_history=False)

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_consumes_inbox_messages(self, mock_config, stage, mock_bridge, mock_processed):
        """Should consume inbox messages from bridge"""
        mock_config.bot.bot.persistence_enabled = True
        mock_bridge.consume.return_value = [
            {"id": "msg1", "from_sid": "qq:dm:other", "content": "Hello"},
            {"id": "msg2", "from_sid": "qq:gm:group1", "content": "Hi"}
        ]

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        mock_bridge.consume.assert_called_once_with("qq:dm:user123")
        assert len(ctx.inbox_msgs) == 2
        assert ctx.inbox_msgs[0]["content"] == "Hello"

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_gets_accessible_sessions(self, mock_config, stage, mock_bridge, mock_processed):
        """Should get accessible sessions from bridge"""
        mock_config.bot.bot.persistence_enabled = True
        mock_bridge.list_accessible.return_value = ["qq:dm:friend1", "qq:gm:group2"]

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        mock_bridge.list_accessible.assert_called_once_with("qq:dm:user123")
        assert ctx.accessible_sessions == ["qq:dm:friend1", "qq:gm:group2"]

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_without_persistence(self, mock_config, stage, mock_session_manager, mock_chat_llm, mock_processed):
        """Should still generate sid when persistence disabled"""
        mock_config.bot.bot.persistence_enabled = False
        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        # sid should still be generated for locking
        assert ctx.sid == "qq:dm:user123"
        # session_enabled should default to True
        assert ctx.session_enabled is True
        # Should not call session manager
        mock_session_manager.get_or_create.assert_not_called()

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_without_session_manager(self, mock_config, mock_chat_llm, mock_bridge, mock_processed):
        """Should handle missing session manager gracefully"""
        mock_config.bot.bot.persistence_enabled = True
        stage = SessionInitStage(None, mock_chat_llm, mock_bridge)

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        # Should still generate sid
        assert ctx.sid == "qq:dm:user123"
        # Should default to enabled
        assert ctx.session_enabled is True

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_without_chat_llm(self, mock_config, mock_session_manager, mock_bridge, mock_processed):
        """Should handle missing chat_llm gracefully"""
        mock_config.bot.bot.persistence_enabled = True
        stage = SessionInitStage(mock_session_manager, None, mock_bridge)

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        # Should not raise
        await stage.process(ctx)
        assert ctx.sid == "qq:dm:user123"

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_without_bridge(self, mock_config, mock_session_manager, mock_chat_llm, mock_processed):
        """Should handle missing bridge gracefully"""
        mock_config.bot.bot.persistence_enabled = True
        stage = SessionInitStage(mock_session_manager, mock_chat_llm, None)

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        # Should not raise
        await stage.process(ctx)
        assert ctx.sid == "qq:dm:user123"
        assert ctx.inbox_msgs == []
        assert ctx.accessible_sessions == []

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_empty_inbox(self, mock_config, stage, mock_bridge, mock_processed):
        """Should handle empty inbox"""
        mock_config.bot.bot.persistence_enabled = True
        mock_bridge.consume.return_value = []

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "user123"

        await stage.process(ctx)

        assert ctx.inbox_msgs == []

    @pytest.mark.asyncio
    @patch('core.pipeline.stages.session_init.config_loader')
    async def test_process_wechat_platform(self, mock_config, stage, mock_processed):
        """Should handle WeChat platform correctly"""
        mock_config.bot.bot.persistence_enabled = True
        mock_processed.platform = PlatformType.WECHAT

        ctx = PipelineContext(processed=mock_processed)
        ctx.is_group = False
        ctx.target_id = "wxuser123"

        await stage.process(ctx)

        assert ctx.sid == "wechat:dm:wxuser123"
