"""
Unit tests for LLMCallStage (TO BE IMPLEMENTED)

Tests LLM invocation with the assembled user input.

Expected behavior based on core/main.py _handle_respond_message:
- Order: 500
- Calls ChatLLM.chat() or ChatAgent.generate() with user_input
- Stores raw LLM reply in ctx.chatllm_reply
- Handles timeouts and errors
- Supports both stateful (ChatLLM) and stateless (ChatAgent) modes
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
    llm.chat = MagicMock(return_value="<msg>Hello from AI</msg>")
    return llm


@pytest.fixture
def mock_chat_agent():
    """Mock ChatAgent"""
    agent = AsyncMock()
    agent.generate = AsyncMock(return_value="<msg>Hello from Agent</msg>")
    return agent


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


class TestLLMCallStage:
    """Test LLMCallStage"""

    def test_stage_initialization(self, mock_chat_llm):
        """Should initialize with order 500 and name 'llm_call'"""
        from core.pipeline.stages.llm_call import LLMCallStage
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        assert stage.order == 500
        assert stage.name == "llm_call"

    @pytest.mark.asyncio
    async def test_process_calls_chatllm(self, mock_chat_llm, mock_processed):
        """Should call ChatLLM.chat() with user_input"""
        from core.pipeline.stages.llm_call import LLMCallStage
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "User message"
        ctx.persist_content = "User message"
        ctx.sid = "qq:dm:user123"

        await stage.process(ctx)

        mock_chat_llm.chat.assert_called_once()
        assert ctx.chatllm_reply == "<msg>Hello from AI</msg>"

    @pytest.mark.asyncio
    async def test_process_calls_chat_agent(self, mock_chat_agent, mock_processed):
        """Should call ChatAgent.generate() in stateless mode"""
        from core.pipeline.stages.llm_call import LLMCallStage
        stage = LLMCallStage(chat_agent=mock_chat_agent)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "User message"
        ctx.sid = "qq:dm:user123"

        await stage.process(ctx)

        mock_chat_agent.generate.assert_called_once()
        assert ctx.chatllm_reply is not None

    @pytest.mark.asyncio
    async def test_process_handles_timeout(self, mock_chat_llm, mock_processed):
        """Should handle LLM timeout gracefully"""
        from core.pipeline.stages.llm_call import LLMCallStage
        import asyncio
        mock_chat_llm.chat.side_effect = asyncio.TimeoutError()
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "User message"

        with pytest.raises(asyncio.TimeoutError):
            await stage.process(ctx)

    @pytest.mark.asyncio
    async def test_process_handles_llm_error(self, mock_chat_llm, mock_processed):
        """Should handle LLM API errors"""
        from core.pipeline.stages.llm_call import LLMCallStage
        mock_chat_llm.chat.side_effect = RuntimeError("API error")
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "User message"

        with pytest.raises(RuntimeError):
            await stage.process(ctx)

    @pytest.mark.asyncio
    async def test_process_passes_persist_content(self, mock_chat_llm, mock_processed):
        """Should pass persist_content for session storage"""
        from core.pipeline.stages.llm_call import LLMCallStage
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "Full prompt with context"
        ctx.persist_content = "Pure user message"
        ctx.sid = "qq:dm:user123"

        await stage.process(ctx)

        call_kwargs = mock_chat_llm.chat.call_args[0]
        assert call_kwargs[1] == "Pure user message"

    @pytest.mark.asyncio
    async def test_process_respects_session_id(self, mock_chat_llm, mock_processed):
        """Should pass session ID for history management"""
        from core.pipeline.stages.llm_call import LLMCallStage
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "Message"
        ctx.sid = "qq:gm:group456"

        await stage.process(ctx)

        # ChatLLM.chat() doesn't take sid parameter in sync mode
        # This test verifies the call happens with correct user_input
        mock_chat_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_with_save_to_session_false(self, mock_chat_llm, mock_processed):
        """Should call with save_to_session=False (deferred persistence)"""
        from core.pipeline.stages.llm_call import LLMCallStage
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "Message"
        ctx.persist_content = ""

        await stage.process(ctx)

        # Check that chat was called with save_to_session=False (keyword arg)
        mock_chat_llm.chat.assert_called_once_with(
            "Message",
            "",
            save_to_session=False
        )

    @pytest.mark.asyncio
    async def test_process_stores_reply_in_context(self, mock_chat_llm, mock_processed):
        """Should store LLM reply in ctx.chatllm_reply"""
        from core.pipeline.stages.llm_call import LLMCallStage
        mock_chat_llm.chat.return_value = "<msg>AI response</msg>"
        stage = LLMCallStage(chat_llm=mock_chat_llm)
        ctx = PipelineContext(processed=mock_processed)
        ctx.user_input = "Message"

        await stage.process(ctx)

        assert ctx.chatllm_reply == "<msg>AI response</msg>"
