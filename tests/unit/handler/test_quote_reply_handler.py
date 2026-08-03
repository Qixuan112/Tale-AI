"""
Unit tests for QuoteReplyHandler

Tests quote reply handling logic:
- Detects messages with reply_to field
- Checks if quoted message is from bot (using cache)
- Passes non-quote messages to next handler
- Chain delegation behavior
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
from core.handler import QuoteReplyHandler


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


class TestQuoteReplyHandler:
    """Test suite for QuoteReplyHandler"""

    def setup_method(self):
        """Setup test fixtures"""
        self.user_id = "user123"
        self.group_id = "group456"
        self.cache = SimpleSentMessageCache()

    def create_message(self, text=None, reply_to=None, group_id=None):
        """Helper to create test messages"""
        return ProcessedMessage(
            platform=PlatformType.QQ,
            event_type=EventType.GROUP_MESSAGE if group_id else EventType.PRIVATE_MESSAGE,
            message_id="msg001",
            sender_id=self.user_id,
            sender_name="TestUser",
            text=text,
            reply_to=reply_to,
            group_id=group_id
        )

    # Basic quote detection tests

    def test_quote_bot_message_triggers_response(self):
        """Test that quoting bot's message triggers response"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    def test_quote_non_bot_message_does_not_trigger(self):
        """Test that quoting non-bot message does not trigger"""
        # Message not in cache = not from bot
        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="user_msg_456",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_no_reply_to_does_not_trigger(self):
        """Test that message without reply_to does not trigger"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="Hello",
            reply_to=None,
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_empty_reply_to_does_not_trigger(self):
        """Test that empty reply_to does not trigger"""
        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="Hello",
            reply_to="",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    # Feature flag tests

    def test_quote_wake_disabled_does_not_trigger(self):
        """Test that quote wake doesn't trigger when feature disabled"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=False,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_quote_wake_disabled_passes_to_next(self):
        """Test that disabled quote wake passes to next handler"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=False,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

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
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert next_handler.called
        assert result.reason == "next_handler_called"

    # Cache tests

    def test_no_cache_does_not_trigger(self):
        """Test that quote reply doesn't trigger without cache"""
        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=None
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_empty_cache_does_not_trigger(self):
        """Test that empty cache does not trigger"""
        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache  # Empty cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision != ResponseDecision.RESPOND

    def test_multiple_messages_in_cache(self):
        """Test cache lookup with multiple messages"""
        self.cache.add("bot_msg_1")
        self.cache.add("bot_msg_2")
        self.cache.add("bot_msg_3")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        # Quote middle message
        message = self.create_message(
            text="About that...",
            reply_to="bot_msg_2",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    # Private vs group message tests

    def test_quote_in_private_message_triggers(self):
        """Test that quote reply works in private messages"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=None  # Private message
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    def test_quote_in_group_message_triggers(self):
        """Test that quote reply works in group messages"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    # Chain delegation tests

    def test_passes_to_next_when_no_reply(self):
        """Test that message without reply passes to next handler"""
        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

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
            text="Hello",
            reply_to=None,
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert next_handler.called
        assert result.reason == "next_handler_called"

    def test_passes_to_next_when_quoting_non_bot(self):
        """Test that quoting non-bot message passes to next handler"""
        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

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
            text="I agree",
            reply_to="user_msg_456",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert next_handler.called
        assert result.reason == "next_handler_called"

    def test_does_not_pass_to_next_when_quoting_bot(self):
        """Test that quoting bot message does not pass to next handler"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

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
            text="I agree",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert not next_handler.called
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    def test_no_next_handler_returns_message(self):
        """Test that handler returns message when no next handler"""
        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="Hello",
            reply_to=None,
            group_id=self.group_id
        )
        result = handler.handle(message)

        # Should return message unchanged
        assert result is message

    # Edge cases

    def test_none_text_with_quote_still_triggers(self):
        """Test that None text doesn't prevent quote reply trigger"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text=None,
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        # Quote reply should work even without text
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    def test_empty_text_with_quote_still_triggers(self):
        """Test that empty text doesn't prevent quote reply trigger"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="",
            reply_to="bot_msg_123",
            group_id=self.group_id
        )
        result = handler.handle(message)

        # Quote reply should work even with empty text
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    def test_special_characters_in_message_id(self):
        """Test that special characters in message ID work correctly"""
        special_id = "bot_msg_!@#$%^&*()"
        self.cache.add(special_id)

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="Reply",
            reply_to=special_id,
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    def test_unicode_in_message_id(self):
        """Test that unicode characters in message ID work correctly"""
        unicode_id = "bot_msg_你好_世界"
        self.cache.add(unicode_id)

        config = ProcessorConfig(
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        handler = QuoteReplyHandler(config)

        message = self.create_message(
            text="Reply",
            reply_to=unicode_id,
            group_id=self.group_id
        )
        result = handler.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"
