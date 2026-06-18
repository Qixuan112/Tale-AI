"""
Thread-safe singleton for storing bot's sent message IDs.

Used by the quote-wake feature to detect when someone replies to
a message that was sent by the bot.
"""

import threading
from collections import OrderedDict


class SentMessageCache:
    """Thread-safe set-based cache of message IDs sent by the bot.

    Maintains a maximum of *maxlen* entries.  When the cache is full
    the oldest entry is evicted (FIFO).
    """

    def __init__(self, maxlen: int = 10000):
        self._ids: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.Lock()
        self._maxlen = maxlen

    def add(self, message_id: str) -> None:
        with self._lock:
            self._ids[message_id] = None
            while len(self._ids) > self._maxlen:
                self._ids.popitem(last=False)

    def contains(self, message_id: str) -> bool:
        with self._lock:
            return message_id in self._ids


sent_message_cache = SentMessageCache()
