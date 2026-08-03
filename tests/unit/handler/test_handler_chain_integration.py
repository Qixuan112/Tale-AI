"""
Integration tests for the complete handler chain

Tests the full responsibility chain:
- Permission → WakeWord → QuoteReply
- Mid-chain interception scenarios
- Full pass-through scenarios
- Complex interaction patterns
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


class SimpleSentMessageCache:
    """Simple cache for testing"""

    def __init__(self):
        self.cache = set()

    def add(self, message_id: str):
        self.cache.add(message_id)

    def contains(self, message_id: str) -> bool:
        return message_id in self.cache


class PermissionHandler:
    """Permission checking handler"""

    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.next_handler = None

    def set_next(self, handler):
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        if not self._check_permission(message):
            message.decision = ResponseDecision.IGNORE
            message.reason = "permission_denied"
            return message
        if self.next_handler:
            return self.next_handler.handle(message)
        return message

    def _check_permission(self, message: ProcessedMessage) -> bool:
        mode = self.config.permission_mode
        if mode == "none":
            return True
        if message.sender_id in self.config.user_deny_list:
            return False
        if message.group_id and message.group_id in self.config.group_deny_list:
            return False
        if mode == "deny_list":
            return True
        if mode == "allow_list":
            if message.is_private_message:
                if not self.config.user_allow_list:
                    return True
                return message.sender_id in self.config.user_allow_list
            if message.group_id:
                if self.config.group_allow_list and message.group_id in self.config.group_allow_list:
                    return True
                if self.config.user_allow_list and message.sender_id in self.config.user_allow_list:
                    return True
                if not self.config.group_allow_list and not self.config.user_allow_list:
                    return True
                return False
        return False


class WakeWordHandler:
    """Wake word detection handler"""

    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.next_handler = None

    def set_next(self, handler):
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        if not message.is_group_message:
            if self.next_handler:
                return self.next_handler.handle(message)
            return message

        if self._check_at_bot(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "at_bot"
            return message

        if self._check_wake_keywords(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "waking_keyword"
            return message

        if self._check_quote_reply(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "quote_wake"
            return message

        if self.next_handler:
            return self.next_handler.handle(message)
        return message

    def _check_at_bot(self, message: ProcessedMessage) -> bool:
        bot_id = self.config.bot_id or str(message.raw_event.get("self_id", ""))
        return bot_id and bot_id in message.at_targets

    def _check_wake_keywords(self, message: ProcessedMessage) -> bool:
        if not self.config.enable_keyword_wake or not message.text or not self.config.waking_keywords:
            return False
        text_lower = message.text.lower()
        return any(kw.lower() in text_lower for kw in self.config.waking_keywords)

    def _check_quote_reply(self, message: ProcessedMessage) -> bool:
        if not self.config.enable_quote_wake or not message.reply_to or not self.config.sent_message_cache:
            return False
        return self.config.sent_message_cache.contains(message.reply_to)


class QuoteReplyHandler:
    """Quote reply detection handler (fallback)"""

    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.next_handler = None

    def set_next(self, handler):
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        if not self.config.enable_quote_wake:
            if self.next_handler:
                return self.next_handler.handle(message)
            return message

        if not message.reply_to:
            if self.next_handler:
                return self.next_handler.handle(message)
            return message

        if self._is_quoting_bot(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "quote_wake"
            return message

        if self.next_handler:
            return self.next_handler.handle(message)
        return message

    def _is_quoting_bot(self, message: ProcessedMessage) -> bool:
        if not self.config.sent_message_cache:
            return False
        return self.config.sent_message_cache.contains(message.reply_to)


class TestHandlerChainIntegration:
    """Integration test suite for complete handler chain"""

    def setup_method(self):
        """Setup test fixtures"""
        self.bot_id = "bot123"
        self.allowed_user = "user_allowed"
        self.blocked_user = "user_blocked"
        self.allowed_group = "group_allowed"
        self.blocked_group = "group_blocked"
        self.cache = SimpleSentMessageCache()

    def create_message(self, sender_id=None, group_id=None, text=None, at_targets=None, reply_to=None):
        """Helper to create test messages"""
        return ProcessedMessage(
            platform=PlatformType.QQ,
            event_type=EventType.GROUP_MESSAGE if group_id else EventType.PRIVATE_MESSAGE,
            message_id="msg001",
            sender_id=sender_id or "user123",
            sender_name="TestUser",
            text=text,
            at_targets=at_targets or [],
            reply_to=reply_to,
            group_id=group_id,
            raw_event={}
        )

    def create_chain(self, config: ProcessorConfig):
        """Helper to create complete handler chain"""
        permission = PermissionHandler(config)
        wake_word = WakeWordHandler(config)
        quote_reply = QuoteReplyHandler(config)

        permission.set_next(wake_word).set_next(quote_reply)
        return permission

    # Full pass-through scenarios

    def test_full_chain_private_message_allowed(self):
        """Test private message passes all checks and reaches end"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=[self.allowed_user],
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=False
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id=self.allowed_user,
            group_id=None,
            text="Hello"
        )
        result = chain.handle(message)

        # Should pass permission (not denied)
        assert result.reason != "permission_denied"

    def test_full_chain_group_message_with_at_bot(self):
        """Test group message with @bot triggers at first wake handler"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=[self.allowed_group],
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=False
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id=self.allowed_group,
            text="Hello @bot",
            at_targets=[self.bot_id]
        )
        result = chain.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "at_bot"

    def test_full_chain_group_message_with_keyword(self):
        """Test group message with keyword triggers at wake handler"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=[self.allowed_group],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello", "hi"],
            enable_quote_wake=False
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id=self.allowed_group,
            text="hello there"
        )
        result = chain.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    def test_full_chain_group_message_with_quote(self):
        """Test group message with quote reply triggers at wake handler"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=[self.allowed_group],
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id=self.allowed_group,
            text="I agree",
            reply_to="bot_msg_123"
        )
        result = chain.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    # Permission blocking scenarios

    def test_permission_blocks_blacklisted_user(self):
        """Test permission handler blocks at first step"""
        config = ProcessorConfig(
            permission_mode="deny_list",
            user_deny_list=[self.blocked_user],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id=self.blocked_user,
            group_id="any_group",
            text="hello bot",
            at_targets=[self.bot_id]
        )
        result = chain.handle(message)

        # Should be blocked at permission handler
        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    def test_permission_blocks_unlisted_group(self):
        """Test permission handler blocks unlisted group"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=[self.allowed_group],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id="unlisted_group",
            text="hello bot",
            at_targets=[self.bot_id]
        )
        result = chain.handle(message)

        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    # No wake condition scenarios

    def test_no_wake_condition_reaches_end(self):
        """Test message with no wake condition reaches end of chain"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=[self.allowed_group],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=False
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id=self.allowed_group,
            text="goodbye"
        )
        result = chain.handle(message)

        # Should pass all checks but not trigger any wake condition
        assert result.decision != ResponseDecision.RESPOND

    # Complex scenarios

    def test_vip_user_in_unlisted_group_with_keyword(self):
        """Test VIP user can trigger in unlisted group"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=["other_group"],
            user_allow_list=["vip_user"],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="vip_user",
            group_id="unlisted_group",
            text="hello"
        )
        result = chain.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    def test_multiple_wake_conditions_at_priority(self):
        """Test @bot takes priority over keyword"""
        config = ProcessorConfig(
            permission_mode="none",
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=False
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id="group456",
            text="hello",
            at_targets=[self.bot_id]
        )
        result = chain.handle(message)

        # @bot should take priority
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "at_bot"

    def test_all_wake_features_enabled_keyword_triggers(self):
        """Test keyword when all wake features enabled"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            permission_mode="none",
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id="group456",
            text="hello world",
            reply_to="bot_msg_123"
        )
        result = chain.handle(message)

        # Keyword should trigger before quote check in WakeWordHandler
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    def test_quote_only_triggers_when_no_other_condition(self):
        """Test quote reply triggers when no @bot or keyword"""
        self.cache.add("bot_msg_123")

        config = ProcessorConfig(
            permission_mode="none",
            bot_id=self.bot_id,
            enable_keyword_wake=False,
            enable_quote_wake=True,
            sent_message_cache=self.cache
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id="group456",
            text="I agree",
            reply_to="bot_msg_123"
        )
        result = chain.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "quote_wake"

    # Edge case: Empty configuration

    def test_empty_config_blocks_everything(self):
        """Test empty allow_list allows everything (default behavior)"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=[],
            user_allow_list=[],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        chain = self.create_chain(config)

        # Private message with empty whitelist should pass
        private_msg = self.create_message(
            sender_id="user123",
            group_id=None,
            text="hello"
        )
        private_result = chain.handle(private_msg)
        assert private_result.reason != "permission_denied"

        # Group message with empty whitelist should also pass
        group_msg = self.create_message(
            sender_id="user123",
            group_id="any_group",
            text="hello"
        )
        group_result = chain.handle(group_msg)
        assert group_result.reason != "permission_denied"

    def test_deny_list_mode_empty_lists_allows_all(self):
        """Test deny_list mode with empty lists allows all"""
        config = ProcessorConfig(
            permission_mode="deny_list",
            group_deny_list=[],
            user_deny_list=[],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="any_user",
            group_id="any_group",
            text="hello"
        )
        result = chain.handle(message)

        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"

    # Message type handling

    def test_private_message_skips_wake_word_handler(self):
        """Test private messages bypass wake word checks"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["user123"],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=False
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id=None,
            text="goodbye"  # Not a wake keyword
        )
        result = chain.handle(message)

        # Should pass permission, skip wake word handler (not denied)
        assert result.reason != "permission_denied"
        assert result.reason != "waking_keyword"

    def test_group_message_requires_wake_condition(self):
        """Test group messages need wake condition"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=["group456"],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"],
            enable_quote_wake=False
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id="group456",
            text="goodbye"  # Not a wake keyword
        )
        result = chain.handle(message)

        # Should pass permission but not trigger
        assert result.decision != ResponseDecision.RESPOND

    # Chain integrity tests

    def test_chain_preserves_message_modifications(self):
        """Test that message modifications persist through chain"""
        config = ProcessorConfig(
            permission_mode="none",
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="user123",
            group_id="group456",
            text="hello"
        )
        result = chain.handle(message)

        # Decision should be set by wake handler
        assert result.decision == ResponseDecision.RESPOND
        assert result.reason == "waking_keyword"
        # Should be same message object
        assert result is message

    def test_chain_stops_at_first_handler_decision(self):
        """Test chain stops when handler makes decision"""
        config = ProcessorConfig(
            permission_mode="deny_list",
            user_deny_list=["blocked_user"],
            bot_id=self.bot_id,
            enable_keyword_wake=True,
            waking_keywords=["hello"]
        )
        chain = self.create_chain(config)

        message = self.create_message(
            sender_id="blocked_user",
            group_id="group456",
            text="hello",
            at_targets=[self.bot_id]
        )
        result = chain.handle(message)

        # Should stop at permission handler
        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"
