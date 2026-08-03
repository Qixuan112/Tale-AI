"""
PermissionHandler - checks message permissions

Applies allow/deny list rules:
- Blacklist priority: deny_list checked first
- Whitelist mode: only listed users/groups allowed
- Empty lists: permissive by default
"""

from typing import Optional
from core.adapter.message_processor import (
    ProcessedMessage,
    ResponseDecision,
    ProcessorConfig
)


class PermissionHandler:
    """Handler for permission checking

    Checks message against allow/deny lists and passes to next
    handler if permission granted.
    """

    def __init__(self, config: ProcessorConfig):
        """Initialize with processor config

        Args:
            config: Processor configuration with permission rules
        """
        self.config = config
        self.next_handler: Optional['PermissionHandler'] = None

    def set_next(self, handler: 'PermissionHandler') -> 'PermissionHandler':
        """Set next handler in chain

        Args:
            handler: Next handler to call

        Returns:
            The handler (for fluent chaining)
        """
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        """Check permissions and pass to next if allowed

        Args:
            message: Message to check

        Returns:
            Processed message with decision
        """
        if not self._check_permission(message):
            message.decision = ResponseDecision.IGNORE
            message.reason = "permission_denied"
            return message

        # Permission granted, pass to next handler
        if self.next_handler:
            return self.next_handler.handle(message)

        return message

    def _check_permission(self, message: ProcessedMessage) -> bool:
        """Check if message passes permission rules

        Args:
            message: Message to check

        Returns:
            True if allowed, False if denied
        """
        mode = self.config.permission_mode

        if mode == "none":
            return True

        # Check blacklists first (priority over whitelists)
        if message.sender_id in self.config.user_deny_list:
            return False

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
