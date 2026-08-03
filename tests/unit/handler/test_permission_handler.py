"""
Unit tests for PermissionHandler

Tests permission checking logic:
- Blacklist (deny_list) mode: reject listed users/groups
- Whitelist (allow_list) mode: only accept listed users/groups
- Empty list behavior
- Chain delegation after permission check
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


class PermissionHandler:
    """Handler for permission checking (mock implementation for testing)"""

    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.next_handler = None

    def set_next(self, handler):
        """Set the next handler in the chain"""
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        """Check permissions and pass to next handler if allowed"""
        if not self._check_permission(message):
            message.decision = ResponseDecision.IGNORE
            message.reason = "permission_denied"
            return message

        # Permission granted, pass to next handler
        if self.next_handler:
            return self.next_handler.handle(message)

        return message

    def _check_permission(self, message: ProcessedMessage) -> bool:
        """Check if message passes permission rules"""
        mode = self.config.permission_mode

        if mode == "none":
            return True

        # Check user blacklist
        if message.sender_id in self.config.user_deny_list:
            return False

        # Check group blacklist
        if message.group_id and message.group_id in self.config.group_deny_list:
            return False

        if mode == "deny_list":
            # Blacklist mode: not in blacklist = allowed
            return True

        if mode == "allow_list":
            # Whitelist mode: must be in whitelist

            # Private message: check user whitelist
            if message.is_private_message:
                if not self.config.user_allow_list:
                    return True  # Empty whitelist = allow all
                return message.sender_id in self.config.user_allow_list

            # Group message: check group or user whitelist
            if message.group_id:
                if self.config.group_allow_list:
                    if message.group_id in self.config.group_allow_list:
                        return True
                if self.config.user_allow_list:
                    if message.sender_id in self.config.user_allow_list:
                        return True
                # Both whitelists empty = allow all
                if not self.config.group_allow_list and not self.config.user_allow_list:
                    return True
                return False

        return False  # Unknown mode = fail closed


class TestPermissionHandler:
    """Test suite for PermissionHandler"""

    def setup_method(self):
        """Setup test fixtures"""
        self.user_id = "user123"
        self.group_id = "group456"

    def create_message(self, sender_id=None, group_id=None):
        """Helper to create test messages"""
        return ProcessedMessage(
            platform=PlatformType.QQ,
            event_type=EventType.GROUP_MESSAGE if group_id else EventType.PRIVATE_MESSAGE,
            message_id="msg001",
            sender_id=sender_id if sender_id is not None else self.user_id,
            sender_name="TestUser",
            text="Hello world",
            group_id=group_id
        )

    # Blacklist (deny_list) mode tests

    def test_deny_list_mode_allows_unlisted_user(self):
        """Test deny_list allows users not in blacklist"""
        config = ProcessorConfig(
            permission_mode="deny_list",
            user_deny_list=["blocked_user"],
            group_deny_list=[]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="allowed_user")
        result = handler.handle(message)

        # Permission check should pass (not denied)
        assert result.reason != "permission_denied"

    def test_deny_list_mode_blocks_listed_user(self):
        """Test deny_list blocks users in blacklist"""
        config = ProcessorConfig(
            permission_mode="deny_list",
            user_deny_list=["blocked_user"],
            group_deny_list=[]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="blocked_user")
        result = handler.handle(message)

        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    def test_deny_list_mode_blocks_listed_group(self):
        """Test deny_list blocks groups in blacklist"""
        config = ProcessorConfig(
            permission_mode="deny_list",
            user_deny_list=[],
            group_deny_list=["blocked_group"]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="user123", group_id="blocked_group")
        result = handler.handle(message)

        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    def test_deny_list_mode_empty_blacklist_allows_all(self):
        """Test deny_list with empty blacklist allows all"""
        config = ProcessorConfig(
            permission_mode="deny_list",
            user_deny_list=[],
            group_deny_list=[]
        )
        handler = PermissionHandler(config)

        message = self.create_message()
        result = handler.handle(message)

        # Permission check should pass (not denied)
        assert result.reason != "permission_denied"

    # Whitelist (allow_list) mode tests

    def test_allow_list_mode_blocks_unlisted_user_private(self):
        """Test allow_list blocks unlisted users in private chat"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["allowed_user"],
            group_allow_list=[]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="unlisted_user", group_id=None)
        result = handler.handle(message)

        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    def test_allow_list_mode_allows_listed_user_private(self):
        """Test allow_list allows listed users in private chat"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["allowed_user"],
            group_allow_list=[]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="allowed_user", group_id=None)
        result = handler.handle(message)

        # Permission check should pass (not denied)
        assert result.reason != "permission_denied"

    def test_allow_list_mode_empty_whitelist_allows_all_private(self):
        """Test allow_list with empty whitelist allows all private messages"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=[],
            group_allow_list=[]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="any_user", group_id=None)
        result = handler.handle(message)

        # Permission check should pass (not denied)
        assert result.reason != "permission_denied"

    def test_allow_list_mode_allows_listed_group(self):
        """Test allow_list allows listed groups"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=[],
            group_allow_list=["allowed_group"]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="any_user", group_id="allowed_group")
        result = handler.handle(message)

        # Permission check should pass (not denied)
        assert result.reason != "permission_denied"

    def test_allow_list_mode_blocks_unlisted_group(self):
        """Test allow_list blocks unlisted groups"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=[],
            group_allow_list=["allowed_group"]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="any_user", group_id="unlisted_group")
        result = handler.handle(message)

        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    def test_allow_list_mode_allows_listed_user_in_unlisted_group(self):
        """Test allow_list allows whitelisted users even in unlisted groups"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["vip_user"],
            group_allow_list=["allowed_group"]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="vip_user", group_id="unlisted_group")
        result = handler.handle(message)

        # Permission check should pass (not denied)
        assert result.reason != "permission_denied"

    def test_allow_list_mode_empty_whitelist_allows_all_groups(self):
        """Test allow_list with empty whitelist allows all group messages"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=[],
            group_allow_list=[]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="any_user", group_id="any_group")
        result = handler.handle(message)

        # Permission check should pass (not denied)
        assert result.reason != "permission_denied"

    # Mode "none" tests

    def test_none_mode_allows_all(self):
        """Test none mode allows all messages"""
        config = ProcessorConfig(
            permission_mode="none",
            user_deny_list=["blocked_user"],
            group_deny_list=["blocked_group"]
        )
        handler = PermissionHandler(config)

        # Should allow blocked user
        message1 = self.create_message(sender_id="blocked_user")
        result1 = handler.handle(message1)
        assert result1.reason != "permission_denied"

        # Should allow blocked group
        message2 = self.create_message(group_id="blocked_group")
        result2 = handler.handle(message2)
        assert result2.reason != "permission_denied"

    # Blacklist priority tests (blacklist overrides whitelist)

    def test_deny_list_overrides_allow_list_for_user(self):
        """Test user blacklist takes priority over user whitelist"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["user123"],
            user_deny_list=["user123"]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="user123", group_id=None)
        result = handler.handle(message)

        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    def test_deny_list_overrides_allow_list_for_group(self):
        """Test group blacklist takes priority over group whitelist"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            group_allow_list=["group456"],
            group_deny_list=["group456"]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="user123", group_id="group456")
        result = handler.handle(message)

        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    # Chain delegation tests

    def test_passes_to_next_handler_when_allowed(self):
        """Test message passes to next handler when permission granted"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["user123"]
        )
        handler = PermissionHandler(config)

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

        message = self.create_message(sender_id="user123", group_id=None)
        result = handler.handle(message)

        assert next_handler.called
        assert result.reason == "next_handler_called"

    def test_does_not_pass_to_next_when_denied(self):
        """Test message does not pass to next handler when permission denied"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["allowed_user"]
        )
        handler = PermissionHandler(config)

        # Mock next handler
        class NextHandler:
            def __init__(self):
                self.called = False

            def handle(self, message):
                self.called = True
                return message

        next_handler = NextHandler()
        handler.set_next(next_handler)

        message = self.create_message(sender_id="blocked_user", group_id=None)
        result = handler.handle(message)

        assert not next_handler.called
        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"

    # Edge cases

    def test_none_values_in_lists(self):
        """Test handling of None values in allow/deny lists"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["user123", None],
            user_deny_list=[None]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="user123")
        result = handler.handle(message)

        # Should still work correctly (not denied)
        assert result.reason != "permission_denied"

    def test_empty_string_user_id(self):
        """Test handling of empty string user ID"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=[""]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="", group_id=None)
        result = handler.handle(message)

        # Empty string should match (not denied)
        assert result.reason != "permission_denied"

    def test_case_sensitive_matching(self):
        """Test that user/group ID matching is case-sensitive"""
        config = ProcessorConfig(
            permission_mode="allow_list",
            user_allow_list=["User123"]
        )
        handler = PermissionHandler(config)

        message = self.create_message(sender_id="user123", group_id=None)
        result = handler.handle(message)

        # Should not match (case-sensitive)
        assert result.decision == ResponseDecision.IGNORE
        assert result.reason == "permission_denied"
