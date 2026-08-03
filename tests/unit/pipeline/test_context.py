"""
Unit tests for PipelineContext

Tests the data class that flows through all pipeline stages.
"""
import pytest
from core.pipeline.context import PipelineContext


class TestPipelineContext:
    """Test PipelineContext data class"""

    def test_create_minimal_context(self, mock_processed):
        """Should create context with minimal required fields"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.processed == mock_processed
        assert ctx.adapter_instance is None
        assert ctx.sid is None
        assert ctx.session_enabled is True
        assert ctx.is_group is False
        assert ctx.target_id == ""
        assert ctx.platform_name == ""

    def test_create_context_with_optional_fields(self, mock_processed):
        """Should create context with all optional fields"""
        ctx = PipelineContext(
            processed=mock_processed,
            adapter_instance="qq_bot_1",
            sid="qq:dm:user123",
            session_enabled=False,
            is_group=True,
            target_id="group456",
            platform_name="QQ"
        )

        assert ctx.adapter_instance == "qq_bot_1"
        assert ctx.sid == "qq:dm:user123"
        assert ctx.session_enabled is False
        assert ctx.is_group is True
        assert ctx.target_id == "group456"
        assert ctx.platform_name == "QQ"

    def test_user_input_fields_default_empty(self, mock_processed):
        """User input fields should default to empty strings"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.user_text == ""
        assert ctx.persist_content == ""
        assert ctx.user_input == ""

    def test_inbox_fields_default_empty(self, mock_processed):
        """Inbox fields should default to empty lists"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.inbox_msgs == []
        assert ctx.accessible_sessions == []

    def test_llm_fields_default_none(self, mock_processed):
        """LLM-related fields should default to None"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.chatllm_reply is None
        assert ctx.parsed is None

    def test_message_fields_default_empty(self, mock_processed):
        """Message fields should default to empty lists"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.messages_to_send == []
        assert ctx.failed_files == []

    def test_control_flags_default_false(self, mock_processed):
        """Control flow flags should default to False"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.should_stop is False
        assert ctx.skip_reply is False

    def test_extra_field_default_empty(self, mock_processed):
        """Extra field should default to empty dict"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.extra == {}

    def test_stop_method_sets_flag(self, mock_processed):
        """stop() should set should_stop to True"""
        ctx = PipelineContext(processed=mock_processed)

        assert ctx.should_stop is False
        ctx.stop()
        assert ctx.should_stop is True

    def test_context_is_mutable(self, mock_processed):
        """Context fields should be mutable during pipeline execution"""
        ctx = PipelineContext(processed=mock_processed)

        # Stages can modify fields
        ctx.sid = "qq:dm:user123"
        ctx.user_text = "Test message"
        ctx.chatllm_reply = "AI response"
        ctx.messages_to_send.append("msg1")
        ctx.extra["custom"] = "value"

        assert ctx.sid == "qq:dm:user123"
        assert ctx.user_text == "Test message"
        assert ctx.chatllm_reply == "AI response"
        assert len(ctx.messages_to_send) == 1
        assert ctx.extra["custom"] == "value"

    def test_inbox_messages_can_be_populated(self, mock_processed):
        """Inbox messages can be added to context"""
        ctx = PipelineContext(processed=mock_processed)

        ctx.inbox_msgs = [
            {"from_sid": "qq:dm:other", "content": "Hello"},
            {"from_sid": "qq:gm:group1", "content": "Hi there"}
        ]
        ctx.accessible_sessions = ["qq:dm:other", "qq:gm:group1"]

        assert len(ctx.inbox_msgs) == 2
        assert len(ctx.accessible_sessions) == 2

    def test_parsed_can_store_dict(self, mock_processed):
        """parsed field can store parsed XML result"""
        ctx = PipelineContext(processed=mock_processed)

        ctx.parsed = {
            "messages": ["Hello"],
            "skip_reply": False,
            "parse_error": False,
            "session_sends": []
        }

        assert ctx.parsed["messages"] == ["Hello"]
        assert ctx.parsed["skip_reply"] is False
