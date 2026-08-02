from collections import OrderedDict
import threading
import time
from typing import Optional


class BoundedCache:
    """
    Thread-safe bounded cache with LRU eviction and optional TTL expiration.

    Features:
    - Maximum size limit with LRU eviction
    - Optional time-to-live (TTL) for entries
    - Thread-safe operations
    - Dict-like interface

    Args:
        maxsize: Maximum number of entries (must be > 0)
        ttl: Time-to-live in seconds (None = no expiration, 0 = immediate expiration)
    """

    def __init__(self, maxsize: int, ttl: Optional[float] = None):
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        if ttl is not None and ttl < 0:
            raise ValueError("ttl must be >= 0 or None")

        self._maxsize = maxsize
        self._ttl = ttl
        self._cache = OrderedDict()
        self._timestamps = {}
        self._lock = threading.Lock()

    def __getitem__(self, key):
        with self._lock:
            self._cleanup_expired()
            if key not in self._cache:
                raise KeyError(key)
            self._cache.move_to_end(key)
            return self._cache[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._cleanup_expired()
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            self._timestamps[key] = time.time()
            if len(self._cache) > self._maxsize:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
                del self._timestamps[oldest]

    def __contains__(self, key):
        with self._lock:
            self._cleanup_expired()
            return key in self._cache

    def get(self, key, default=None):
        """Get value by key, return default if not found."""
        try:
            return self[key]
        except KeyError:
            return default

    def __delitem__(self, key):
        with self._lock:
            del self._cache[key]
            del self._timestamps[key]

    def clear(self):
        """Remove all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def __len__(self):
        with self._lock:
            self._cleanup_expired()
            return len(self._cache)

    def keys(self):
        """Return list of current keys."""
        with self._lock:
            self._cleanup_expired()
            return list(self._cache.keys())

    def __iter__(self):
        """Iterate over keys in the cache."""
        with self._lock:
            self._cleanup_expired()
            return iter(list(self._cache.keys()))

    def _touch(self, key):
        """
        Manually refresh TTL timestamp and LRU position for a key.

        Use this when modifying mutable values in-place (e.g., list.append, dict[k]=v)
        to ensure TTL and LRU are updated correctly.

        Args:
            key: The key to touch

        Raises:
            KeyError: If key is not in cache
        """
        with self._lock:
            if key not in self._cache:
                raise KeyError(key)
            self._timestamps[key] = time.time()
            self._cache.move_to_end(key)

    def _cleanup_expired(self):
        """Remove expired entries based on TTL."""
        if self._ttl is None:
            return
        current_time = time.time()
        expired = [k for k, t in self._timestamps.items()
                   if current_time - t >= self._ttl]
        for key in expired:
            del self._cache[key]
            del self._timestamps[key]
