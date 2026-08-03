"""
Unit tests for HistorySaveStage (TO BE IMPLEMENTED)

Tests session history persistence.

Expected behavior based on core/main.py _handle_respond_message:
- Order: 900
- always_run: True (executes even if pipeline stopped early)
- Saves conversation to session history (both user input and AI reply)
- Acknowledges consumed inbox messages (cross-session)
- Handles both ChatLLM stateful mode and ChatAgent stateless mode
- Only saves final reply (not intermediate tool-calling rounds)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.pipeline.context import PipelineContext
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType


@pytest.fixture
def mock_chat_llm():
    """Mock ChatLLM"""
    llm = MagicMock()
    llm._save_session_memory = MagicMock()
    llm.current_sid = "qq:dm:user123"
    return llm


@pytest.fixture
def mock_chat_agent():
    """Mock ChatAgent"""
    agent = MagicMock()
    return agent


@pytest.fixture
def mock_session_manager():
    """Mock SessionManager"""
    manager = MagicMock()
    manager.append_message = MagicMock()
    return manager


@pytest.fixture
def mock_bridge():
    """Mock BridgeState"""
    bridge = AsyncMock()
    bridge.ack = AsyncMock()
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


class TestHistorySaveStage:
    """Test HistorySaveStage (SKELETON - implementation needed)"""

    @pytest.mark.skip(reason="Stage not yet implemented")
    def test_stage_initialization(self):
        """Should initialize with order 900, name 'history_save', and always_run=True"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(mock_chat_llm, mock_session_manager, mock_bridge)
        # assert stage.order == 900
        # assert stage.name == "history_save"
        # assert stage.always_run is True
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_saves_to_chatllm_session(self, mock_chat_llm, mock_processed):
        """Should save to ChatLLM session memory in stateful mode"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(mock_chat_llm, None, None)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.persist_content = "User message"
        # ctx.chatllm_reply = "<msg>AI reply</msg>"
        #
        # await stage.process(ctx)
        #
        # mock_chat_llm._save_session_memory.assert_called_once_with("User message")
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_saves_to_session_manager(self, mock_session_manager, mock_processed):
        """Should save to SessionManager in persistence mode"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(None, mock_session_manager, None)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.sid = "qq:dm:user123"
        # ctx.persist_content = "User message"
        # ctx.chatllm_reply = "<msg>AI reply</msg>"
        # ctx.parsed = {"messages": ["AI reply"]}
        #
        # await stage.process(ctx)
        #
        # # Should save both user and assistant messages
        # assert mock_session_manager.append_message.call_count >= 1
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_acknowledges_inbox_messages(self, mock_bridge, mock_processed):
        """Should acknowledge consumed inbox messages"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(None, None, mock_bridge)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.sid = "qq:dm:user123"
        # ctx.inbox_msgs = [
        #     {"id": "msg1", "from_sid": "qq:dm:other", "content": "Hello"},
        #     {"id": "msg2", "from_sid": "qq:gm:group1", "content": "Hi"}
        # ]
        #
        # await stage.process(ctx)
        #
        # mock_bridge.ack.assert_called_once_with("qq:dm:user123", ["msg1", "msg2"])
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_runs_even_when_pipeline_stopped(self, mock_chat_llm, mock_processed):
        """Should run even if ctx.should_stop is True (always_run)"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(mock_chat_llm, None, None)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.should_stop = True  # Pipeline stopped early
        # ctx.persist_content = "User message"
        #
        # # Stage should still execute due to always_run=True
        # await stage.process(ctx)
        #
        # mock_chat_llm._save_session_memory.assert_called()
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_skips_without_persist_content(self, mock_chat_llm, mock_processed):
        """Should skip saving when persist_content is empty"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(mock_chat_llm, None, None)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.persist_content = ""
        #
        # await stage.process(ctx)
        #
        # mock_chat_llm._save_session_memory.assert_not_called()
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_handles_chat_agent_mode(self, mock_chat_agent, mock_session_manager, mock_processed):
        """Should handle ChatAgent stateless mode with snapshot persistence"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(None, mock_session_manager, None, chat_agent=mock_chat_agent)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.sid = "qq:dm:user123"
        # ctx.persist_content = "User message"
        # ctx.chatllm_reply = "<msg>AI reply</msg>"
        #
        # await stage.process(ctx)
        #
        # # Should save snapshot to session manager
        # mock_session_manager.append_message.assert_called()
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_acks_only_with_message_ids(self, mock_bridge, mock_processed):
        """Should only ack inbox messages that have 'id' field"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(None, None, mock_bridge)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.sid = "qq:dm:user123"
        # ctx.inbox_msgs = [
        #     {"id": "msg1", "content": "Has ID"},
        #     {"content": "No ID"},  # Missing 'id'
        #     {"id": "msg3", "content": "Has ID"}
        # ]
        #
        # await stage.process(ctx)
        #
        # # Should only ack messages with IDs
        # mock_bridge.ack.assert_called_once_with("qq:dm:user123", ["msg1", "msg3"])
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_without_inbox_messages(self, mock_bridge, mock_processed):
        """Should not call ack when inbox_msgs is empty"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(None, None, mock_bridge)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.sid = "qq:dm:user123"
        # ctx.inbox_msgs = []
        #
        # await stage.process(ctx)
        #
        # mock_bridge.ack.assert_not_called()
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_handles_skip_reply(self, mock_chat_llm, mock_bridge, mock_processed):
        """Should still save and ack even when skip_reply is True"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(mock_chat_llm, None, mock_bridge)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.skip_reply = True
        # ctx.persist_content = "User message"
        # ctx.sid = "qq:dm:user123"
        # ctx.inbox_msgs = [{"id": "msg1", "content": "Hello"}]
        #
        # await stage.process(ctx)
        #
        # # Should still save history and ack
        # mock_chat_llm._save_session_memory.assert_called()
        # mock_bridge.ack.assert_called()
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_without_session_id(self, mock_chat_llm, mock_processed):
        """Should handle missing session ID gracefully"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # stage = HistorySaveStage(mock_chat_llm, None, None)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.sid = None
        # ctx.persist_content = "User message"
        #
        # # Should not crash
        # await stage.process(ctx)
        pass

    @pytest.mark.skip(reason="Stage not yet implemented")
    @pytest.mark.asyncio
    async def test_process_handles_save_errors_gracefully(self, mock_chat_llm, mock_processed):
        """Should not crash if save operation fails"""
        # from core.pipeline.stages.history_save import HistorySaveStage
        # mock_chat_llm._save_session_memory.side_effect = RuntimeError("Save failed")
        # stage = HistorySaveStage(mock_chat_llm, None, None)
        # ctx = PipelineContext(processed=mock_processed)
        # ctx.persist_content = "User message"
        #
        # # Should not raise, just log error
        # await stage.process(ctx)
        pass
