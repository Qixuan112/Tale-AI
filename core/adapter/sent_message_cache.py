"""
Thread-safe singleton for storing bot's sent message IDs.

Used by the quote-wake feature to detect when someone replies to
a message that was sent by the bot.
"""

import threading


class SentMessageCache:
    """Thread-safe set-based cache of message IDs sent by the bot."""

    def __init__(self):
        self._ids: set = set()
        self._lock = threading.Lock()

    def add(self, message_id: str) -> None:
        with self._lock:
            self._ids.add(message_id)

    def contains(self, message_id: str) -> bool:
        with self._lock:
            return message_id in self._ids


sent_message_cache = SentMessageCache()
