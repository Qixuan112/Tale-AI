"""
QuoteReplyHandler - handles quote reply detection

Checks if message quotes a bot message (via sent message cache).
"""

from typing import Optional
from core.adapter.message_processor import (
    ProcessedMessage,
    ResponseDecision,
    ProcessorConfig
)


class QuoteReplyHandler:
    """Handler for quote reply detection

    Checks if message quotes a bot's previous message and
    sets RESPOND decision if found.
    """

    def __init__(self, config: ProcessorConfig):
        """Initialize with processor config

        Args:
            config: Processor configuration with cache
        """
        self.config = config
        self.next_handler: Optional['QuoteReplyHandler'] = None

    def set_next(self, handler: 'QuoteReplyHandler') -> 'QuoteReplyHandler':
        """Set next handler in chain

        Args:
            handler: Next handler to call

        Returns:
            The handler (for fluent chaining)
        """
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        """Check if message quotes bot's message

        Args:
            message: Message to check

        Returns:
            Processed message with decision
        """
        # Check if quote wake is enabled
        if not self.config.enable_quote_wake:
            if self.next_handler:
                return self.next_handler.handle(message)
            return message

        # Check if message has reply_to
        if not message.reply_to:
            if self.next_handler:
                return self.next_handler.handle(message)
            return message

        # Check if quoted message is from bot
        if self._is_quoting_bot(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "quote_wake"
            return message

        # Not quoting bot, pass to next
        if self.next_handler:
            return self.next_handler.handle(message)

        return message

    def _is_quoting_bot(self, message: ProcessedMessage) -> bool:
        """Check if quoted message is from bot

        Args:
            message: Message to check

        Returns:
            True if quoting bot message
        """
        if not self.config.sent_message_cache:
            return False
        return self.config.sent_message_cache.contains(message.reply_to)
