"""
WakeWordHandler - detects wake conditions

Checks for:
- @bot mentions (highest priority)
- Wake keywords in text (case-insensitive)
- Quote replies to bot messages
"""

from typing import Optional
from core.adapter.message_processor import (
    ProcessedMessage,
    ResponseDecision,
    ProcessorConfig
)


class WakeWordHandler:
    """Handler for wake word detection

    Checks if message contains wake conditions (@bot, keywords, quotes)
    and sets RESPOND decision if found.
    """

    def __init__(self, config: ProcessorConfig):
        """Initialize with processor config

        Args:
            config: Processor configuration with wake rules
        """
        self.config = config
        self.next_handler: Optional['WakeWordHandler'] = None

    def set_next(self, handler: 'WakeWordHandler') -> 'WakeWordHandler':
        """Set next handler in chain

        Args:
            handler: Next handler to call

        Returns:
            The handler (for fluent chaining)
        """
        self.next_handler = handler
        return handler

    def handle(self, message: ProcessedMessage) -> ProcessedMessage:
        """Check for wake words/conditions

        Args:
            message: Message to check

        Returns:
            Processed message with decision
        """
        # Only apply to group messages
        if not message.is_group_message:
            if self.next_handler:
                return self.next_handler.handle(message)
            return message

        # Check @bot (highest priority)
        if self._check_at_bot(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "at_bot"
            return message

        # Check wake keywords
        if self._check_wake_keywords(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "waking_keyword"
            return message

        # Check quote reply
        if self._check_quote_reply(message):
            message.decision = ResponseDecision.RESPOND
            message.reason = "quote_wake"
            return message

        # No wake condition met, pass to next
        if self.next_handler:
            return self.next_handler.handle(message)

        return message

    def _check_at_bot(self, message: ProcessedMessage) -> bool:
        """Check if bot is @mentioned

        Args:
            message: Message to check

        Returns:
            True if bot is mentioned
        """
        # Try config bot_id first, fallback to self_id from raw_event
        bot_id = self.config.bot_id or str(message.raw_event.get("self_id", ""))
        if not bot_id:
            return False
        return bot_id in message.at_targets

    def _check_wake_keywords(self, message: ProcessedMessage) -> bool:
        """Check if message contains wake keywords

        Args:
            message: Message to check

        Returns:
            True if wake keyword found (case-insensitive)
        """
        if not self.config.enable_keyword_wake:
            return False
        if not message.text or not self.config.waking_keywords:
            return False

        text_lower = message.text.lower()
        for keyword in self.config.waking_keywords:
            if keyword.lower() in text_lower:
                return True
        return False

    def _check_quote_reply(self, message: ProcessedMessage) -> bool:
        """Check if message is quoting bot's message

        Args:
            message: Message to check

        Returns:
            True if quoting bot message
        """
        if not self.config.enable_quote_wake:
            return False
        if not message.reply_to:
            return False
        if not self.config.sent_message_cache:
            return False
        return self.config.sent_message_cache.contains(message.reply_to)
