"""
Unit tests for ToolExecuteStage (TO BE IMPLEMENTED)

Tests tool/function call execution.

Expected behavior based on core/main.py _handle_respond_message:
- Order: 700
- Executes tool calls from ctx.parsed (both <tool> XML tags and function_call format)
- Calls ToolLLM for function calling or execute_function() directly
- Stores tool results back into context
- May trigger follow-up LLM calls (multi-turn conversation)
- Handles tool execution errors gracefully
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.pipeline.context import PipelineContext
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType
from core.message import Message, Text


@pytest.fixture
def mock_toolllm():
    """Mock ToolLLM"""
    llm = MagicMock()
    llm.call_function = MagicMock(return_value="Tool result")
    llm.generate_fc = MagicMock(return_value='{"function": "test_tool", "arguments": {}}')
    llm.query_tools = MagicMock(return_value="Available tools: tool1, tool2")
    return llm


@pytest.fixture
def mock_processed():
    """Create a basic ProcessedMessage"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        sender_id="user123",
        sender_name="TestUser",
        text="Search for Python",
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


class TestToolExecuteStage:
    """Test ToolExecuteStage"""

    def test_stage_initialization(self, mock_toolllm):
        """Should initialize with order 700 and name 'tool_execute'"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        stage = ToolExecuteStage(tool_llm=mock_toolllm)
        assert stage.order == 700
        assert stage.name == "tool_execute"

    @pytest.mark.asyncio
    async def test_process_executes_tool_call(self, mock_toolllm, mock_processed):
        """Should execute tool from parsed XML"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.message import Message, Text

        # Mock ToolLLM to return function call
        mock_toolllm.generate_fc = MagicMock(return_value='{"function": "browser_search", "arguments": {"query": "test"}}')

        # Mock ChatLLM/Agent for follow-up
        mock_chatllm = MagicMock()
        mock_chatllm.chat = MagicMock(return_value="<msg>Here are the results</msg>")

        stage = ToolExecuteStage(tool_llm=mock_toolllm, chat_llm=mock_chatllm, max_steps=2)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg>Searching...</msg><act>browser_search</act>"
        ctx.parsed = {
            "messages": [Message().add_element(Text("Searching..."))],
            "actions": ["browser_search"],
            "skip_reply": False
        }

        await stage.process(ctx)

        # Tool should be executed
        mock_toolllm.generate_fc.assert_called_once()
        # Follow-up call should happen
        mock_chatllm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_skips_without_tools(self, mock_toolllm, mock_processed):
        """Should skip when no tools in parsed"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.message import Message, Text

        stage = ToolExecuteStage(tool_llm=mock_toolllm, max_steps=2)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg>Just a message</msg>"
        ctx.parsed = {
            "messages": [Message().add_element(Text("Just a message"))],
            "skip_reply": False
        }

        await stage.process(ctx)

        # No tool execution
        mock_toolllm.generate_fc.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_handles_function_call_format(self, mock_toolllm, mock_processed):
        """Should handle OpenAI function_call format"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage

        # Mock ChatLLM for follow-up
        mock_chatllm = MagicMock()
        mock_chatllm.chat = MagicMock(return_value="<msg>Results processed</msg>")

        stage = ToolExecuteStage(tool_llm=mock_toolllm, chat_llm=mock_chatllm, max_steps=2)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = '{"function": "browser_search", "arguments": {"query": "Python"}}'
        ctx.parsed = {
            "messages": [],
            "skip_reply": False
        }

        await stage.process(ctx)

        # Should parse and execute function call, then call follow-up
        mock_chatllm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_stores_tool_results(self, mock_toolllm, mock_processed):
        """Should store tool execution results in context"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.message import Message, Text

        mock_toolllm.generate_fc = MagicMock(return_value='{"function": "browser_search", "arguments": {"query": "test"}}')

        # Mock ChatLLM to return final messages
        mock_chatllm = MagicMock()
        mock_chatllm.chat = MagicMock(return_value="<msg>Search complete</msg>")

        stage = ToolExecuteStage(tool_llm=mock_toolllm, chat_llm=mock_chatllm, max_steps=2)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg>Searching...</msg><act>browser_search</act>"
        ctx.parsed = {
            "messages": [Message().add_element(Text("Searching..."))],
            "actions": ["browser_search"]
        }

        await stage.process(ctx)

        # messages_to_send should be updated with final result
        assert ctx.messages_to_send is not None

    @pytest.mark.asyncio
    async def test_process_handles_tool_error(self, mock_toolllm, mock_processed):
        """Should handle tool execution errors gracefully"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.message import Message, Text

        mock_toolllm.generate_fc = MagicMock(side_effect=RuntimeError("Tool failed"))

        # Mock ChatLLM for follow-up (should still be called with error)
        mock_chatllm = MagicMock()
        mock_chatllm.chat = MagicMock(return_value="<msg>Error handled</msg>")

        stage = ToolExecuteStage(tool_llm=mock_toolllm, chat_llm=mock_chatllm, max_steps=2)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg>Trying...</msg><act>browser_search</act>"
        ctx.parsed = {
            "messages": [Message().add_element(Text("Trying..."))],
            "actions": ["browser_search"]
        }

        # Should not crash
        await stage.process(ctx)

        # Error should be handled, follow-up should be called
        mock_chatllm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_triggers_follow_up_llm(self, mock_toolllm, mock_processed):
        """Should trigger follow-up LLM call with tool results"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.message import Message, Text

        mock_toolllm.generate_fc = MagicMock(return_value='{"function": "browser_search", "arguments": {"query": "test"}}')

        # Mock ChatLLM for follow-up
        mock_chatllm = MagicMock()
        mock_chatllm.chat = MagicMock(return_value="<msg>Result processed</msg>")

        stage = ToolExecuteStage(tool_llm=mock_toolllm, chat_llm=mock_chatllm, max_steps=2)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg>Searching...</msg><act>browser_search</act>"
        ctx.parsed = {
            "messages": [Message().add_element(Text("Searching..."))],
            "actions": ["browser_search"]
        }

        await stage.process(ctx)

        # Follow-up LLM call should happen to process results
        mock_chatllm.chat.assert_called_once()
        # Verify the call contains tool results
        call_args = mock_chatllm.chat.call_args[0][0]
        assert "执行结果" in call_args or "工具" in call_args

    @pytest.mark.asyncio
    async def test_process_multiple_tool_calls(self, mock_toolllm, mock_processed):
        """Should execute multiple tool calls"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.message import Message, Text

        mock_toolllm.generate_fc = MagicMock(return_value='{"function": "browser_search", "arguments": {"query": "test"}}')

        # Mock ChatLLM for follow-up
        mock_chatllm = MagicMock()
        mock_chatllm.chat = MagicMock(return_value="<msg>All tools executed</msg>")

        stage = ToolExecuteStage(tool_llm=mock_toolllm, chat_llm=mock_chatllm, max_steps=2)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg>Running...</msg><act>tool1</act><act>tool2</act><act>tool3</act>"
        ctx.parsed = {
            "messages": [Message().add_element(Text("Running..."))],
            "actions": ["tool1", "tool2", "tool3"]
        }

        await stage.process(ctx)

        # All tools should be executed
        assert mock_toolllm.generate_fc.call_count == 3

    @pytest.mark.asyncio
    async def test_process_respects_max_iterations(self, mock_toolllm, mock_processed):
        """Should limit multi-turn iterations to prevent infinite loops"""
        from core.pipeline.stages.tool_execute import ToolExecuteStage
        from core.message import Message, Text

        mock_toolllm.generate_fc = MagicMock(return_value='{"function": "browser_search", "arguments": {"query": "test"}}')

        # Mock ChatLLM to always return more tool calls (infinite loop scenario)
        mock_chatllm = MagicMock()
        mock_chatllm.chat = MagicMock(return_value="<msg>More work...</msg><act>infinite_tool</act>")

        stage = ToolExecuteStage(tool_llm=mock_toolllm, chat_llm=mock_chatllm, max_steps=3)
        ctx = PipelineContext(processed=mock_processed)
        ctx.chatllm_reply = "<msg>Starting...</msg><act>infinite_tool</act>"
        ctx.parsed = {
            "messages": [Message().add_element(Text("Starting..."))],
            "actions": ["infinite_tool"]
        }

        await stage.process(ctx)

        # Should stop after max_steps (3 iterations total)
        # First iteration + 2 follow-ups = 3 calls
        assert mock_toolllm.generate_fc.call_count <= 3
