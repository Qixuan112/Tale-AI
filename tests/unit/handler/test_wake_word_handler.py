"""
Unit tests for WakeWordHandler

Tests wake word detection logic:
- Keyword matching in message text (case-insensitive)
- @bot detection (bot_id in at_targets)
- Quote reply detection (reply_to message from bot)
- Chain delegation when no match found
"""

import pytest
from datetime import datetime
from core.adapter.event import (
    PlatformEvent, EventType, PlatformType,
    SenderInfo, MessageContent
)
from core.adapter.message_processor import (
    ProcessedMessage, ResponseDecision, ProcessorConfig
)
from core.handler import WakeWordHandler


class SimpleSentMessageCache:
    """Simple cache for testing quote reply detection"""

    def __init__(self):
        self.cache = set()

    def add(self, message_id: str):
        """Add message ID to cache"""
        self.cache.add(message_id)

    def contains(self, message_id: str) -> bool:
        """Check if message ID is in cache"""
        return message_id in self.cache

    def clear(self):
        """Clear cache"""
        self.cache.clear()


class TestWakeWordHandler:
    """Test suite for WakeWordHandler"""

    def setup_method(self):
        """Setup test fixtures"""
        self.bot_id = "bot123"
        self.user_id = "user456"
        self.group_id = "group789"
        self.cache = SimpleSentMessageCache()

    def create_message(self, text=None, at_targets=None, reply_to=None, group_id=None):
        """Helper to create test messages"""
        return ProcessedMessage(
            platform=PlatformType.QQ,
            event_type=EventType.GROUP_MESSAGE if group_id else EventType.PRIVATE_MESSAGE,
            message_id="msg001",
            sender_id=self.user_id,
            sender_name="TestUser",
            text=text,
            at_targets=at_targets or [],
            reply_to=reply_to,
            group_id=group_id,
            raw_event={}
        )

    # @bot detection tests

    def test_at_bot_triggers_response(self):
        """Test that @bot triggers immediate response"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=False
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="Hello @bot",
            at_targets=[self.bot_id],
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "at_bot"

    def test_at_bot_without_bot_id_does_not_trigger(self):
        """Test that @bot check fails when bot_id not configured"""
        config = ProcessorConfig(
            bot_id="",
            enable_keyword_wake=False,
            enable_quote_wake=False
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="Hello @someone",
            at_targets=["someone"],
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_at_bot_uses_self_id_fallback(self):
        """Test that @bot check uses self_id from raw_event as fallback"""
        config = ProcessorConfig(
            bot_id="",  # Empty bot_id
            enable_keyword_wake=False,
            enable_quote_wake=False
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="Hello @bot",
            at_targets=["bot999"],
            group_id=self.group_id
        )
        message.raw_event = {"self_id": "bot999"}

        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "at_bot"

    def test_at_other_user_does_not_trigger(self):
        """Test that @other_user does not trigger bot response"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=False
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="Hello @other",
            at_targets=["other_user"],
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_empty_at_targets_does_not_trigger(self):
        """Test that empty at_targets does not trigger"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=False
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="Hello",
            at_targets=[],
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    # Wake keyword tests

    def test_wake_keyword_triggers_response(self):
        """Test that wake keyword triggers response"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello", "hey"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="hello world",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    def test_wake_keyword_case_insensitive(self):
        """Test that wake keyword matching is case-insensitive"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["HELLO"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="hello world",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    def test_wake_keyword_partial_match(self):
        """Test that wake keyword matches partial strings"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["bot"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="robotics is cool",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    def test_multiple_keywords_any_match(self):
        """Test that any keyword in list triggers response"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello", "hey", "hi"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="hey there",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    def test_wake_keyword_disabled_does_not_trigger(self):
        """Test that keywords don't trigger when feature disabled"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            waking_keywords=["hello"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="hello world",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_empty_keyword_list_does_not_trigger(self):
        """Test that empty keyword list does not trigger"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=[]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="hello world",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_none_text_does_not_trigger_keyword(self):
        """Test that None text does not trigger keyword match"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text=None,
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_empty_text_does_not_trigger_keyword(self):
        """Test that empty text does not trigger keyword match"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    # Quote reply tests

    def test_quote_reply_triggers_response(self):
        """Test that quoting bot's message triggers response"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    def test_quote_reply_non_bot_message_does_not_trigger(self):
        """Test that quoting non-bot message does not trigger"""
        # Don't add message to cache (simulating it's not from bot)

        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="other_msg_456",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_quote_reply_disabled_does_not_trigger(self):
        """Test that quote reply doesn't trigger when feature disabled"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=False,
            sent_message_cache=self.cache
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_quote_reply_without_cache_does_not_trigger(self):
        """Test that quote reply doesn't trigger without cache"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=True,
            sent_message_cache=None
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_no_reply_to_does_not_trigger_quote(self):
        """Test that message without reply_to does not trigger quote wake"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="Hello",
            reply_to=None,
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    # Priority tests (at_bot > keyword > quote_reply)

    def test_at_bot_takes_priority_over_keyword(self):
        """Test that @bot takes priority over keyword"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=False
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="hello bot",
            at_targets=[self.bot_id],
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "at_bot"

    def test_keyword_takes_priority_over_quote_reply(self):
        """Test that keyword takes priority over quote reply"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="hello",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    # Private message bypass tests

    def test_private_message_bypasses_handler(self):
        """Test that private messages bypass wake word checks"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        handler = WakeWordHandler(config)

        message = self.create_message(
            text="some text",
            group_id=None  # Private message
        )
        result = handler.handle(message)

        # Should not be handled by this handler
        assert result.decision != ResponseDecision.RESPOND

    def test_private_message_passes_to_next_handler(self):
        """Test that private messages pass to next handler"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        handler = WakeWordHandler(config)

        # Mock next handler
        class NextHandler:
            def __init__(self):
                self.called = False

            def handle(self, message):
                self.called = True
                message.reason = "next_handler_called"
                return message

        next_handler = NextHandler()
        handler.set_next(next_handler)

        message = self.create_message(
            text="hello",
            group_id=None  # Private message
        )
        result = handler.handle(message)

        assert next_handler.called
        assert result.reason == "next_handler_called"

    # Chain delegation tests

    def test_passes_to_next_when_no_wake_condition(self):
        """Test that message passes to next handler when no wake condition met"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=False
        )
        handler = WakeWordHandler(config)

        # Mock next handler
        class NextHandler:
            def __init__(self):
                self.called = False

            def handle(self, message):
                self.called = True
                message.reason = "next_handler_called"
                return message

        next_handler = NextHandler()
        handler.set_next(next_handler)

        message = self.create_message(
            text="goodbye",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert next_handler.called
        assert result.reason == "next_handler_called"

    def test_does_not_pass_to_next_when_wake_condition_met(self):
        """Test that message does not pass to next when wake condition met"""
        config = ProcessorConfig(
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        handler = WakeWordHandler(config)

        # Mock next handler
        class NextHandler:
            def __init__(self):
                self.called = False

            def handle(self, message):
                self.called = True
                return message

        next_handler = NextHandler()
        handler.set_next(next_handler)

        message = self.create_message(
            text="hello world",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert not next_handler.called
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"
