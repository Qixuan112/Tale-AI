"""
Integration tests for BoundedCache with real usage patterns.

Tests verify that the write-through (copy-on-write) pattern correctly
updates TTL and LRU when modifying mutable values.
"""

import pytest
import time
from core.utils.cache import BoundedCache


# ============================================================================
# 1. Write-Through Pattern Tests (4)
# ============================================================================

def test_chat_context_buffer_write_through_updates_ttl():
    """Test that write-through pattern updates TTL for _chat_context_buffer."""
    cache = BoundedCache(maxsize=10, ttl=0.2)
    key = "group_123"

    # Initial write
    buffer = cache.get(key, [])
    buffer.append({"msg": "hello"})
    cache[key] = buffer

    initial_timestamp = cache._timestamps[key]

    time.sleep(0.1)

    # Write-through: get -> modify -> set
    buffer = cache.get(key, [])
    buffer.append({"msg": "world"})
    cache[key] = buffer

    # TTL should be refreshed
    assert cache._timestamps[key] > initial_timestamp

    time.sleep(0.15)  # Total 0.25s, but last write was at 0.1s

    # Should still be accessible (TTL refreshed to 0.1s, now 0.15s elapsed)
    assert key in cache
    assert len(cache[key]) == 2


def test_chat_context_buffer_write_through_updates_lru():
    """Test that write-through pattern updates LRU for _chat_context_buffer."""
    cache = BoundedCache(maxsize=3)

    cache['a'] = []
    cache['b'] = []
    cache['c'] = []

    # Write-through on 'a'
    buffer = cache.get('a', [])
    buffer.append("item")
    cache['a'] = buffer

    # Add new key - should evict 'b', not 'a'
    cache['d'] = []

    assert 'a' in cache
    assert 'b' not in cache
    assert 'c' in cache
    assert 'd' in cache


def test_name_to_id_write_through_updates_ttl():
    """Test that write-through pattern updates TTL for _name_to_id."""
    cache = BoundedCache(maxsize=10, ttl=0.2)
    group_key = "group_456"

    # Initial write
    name_map = cache.get(group_key, {})
    name_map["Alice"] = "user_001"
    cache[group_key] = name_map

    initial_timestamp = cache._timestamps[group_key]

    time.sleep(0.1)

    # Write-through: get -> modify -> set
    name_map = cache.get(group_key, {})
    name_map["Bob"] = "user_002"
    cache[group_key] = name_map

    # TTL should be refreshed
    assert cache._timestamps[group_key] > initial_timestamp

    time.sleep(0.15)  # Total 0.25s, but last write was at 0.1s

    # Should still be accessible
    assert group_key in cache
    assert len(cache[group_key]) == 2


def test_name_to_id_write_through_updates_lru():
    """Test that write-through pattern updates LRU for _name_to_id."""
    cache = BoundedCache(maxsize=3)

    cache['g1'] = {}
    cache['g2'] = {}
    cache['g3'] = {}

    # Write-through on 'g1'
    name_map = cache.get('g1', {})
    name_map["User"] = "id"
    cache['g1'] = name_map

    # Add new key - should evict 'g2', not 'g1'
    cache['g4'] = {}

    assert 'g1' in cache
    assert 'g2' not in cache
    assert 'g3' in cache
    assert 'g4' in cache


# ============================================================================
# 2. Memory Leak Prevention Tests (3)
# ============================================================================

def test_chat_context_buffer_bounded_with_many_sessions():
    """Test that cache size stays bounded even with many sessions."""
    cache = BoundedCache(maxsize=200, ttl=7200)

    # Simulate 1000 sessions
    for session_id in range(1000):
        key = f"session_{session_id}"

        # Simulate 150 messages with write-through
        buffer = cache.get(key, [])
        for msg_id in range(150):
            buffer.append({
                "sender": f"user_{msg_id % 10}",
                "text": f"Message {msg_id}",
                "time": "12:00"
            })

        # Manual truncation
        if len(buffer) > 100:
            buffer = buffer[-100:]

        cache[key] = buffer

    # Cache size should never exceed maxsize
    assert len(cache) <= 200

    # Check sample entry size
    keys = list(cache.keys())
    if keys:
        assert len(cache[keys[0]]) <= 100


def test_name_to_id_bounded_with_many_groups():
    """Test that cache size stays bounded even with many groups."""
    cache = BoundedCache(maxsize=200, ttl=86400)

    # Simulate 500 groups
    for group_id in range(500):
        group_key = f"group_{group_id}"

        # Simulate 50 users with write-through
        name_map = cache.get(group_key, {})
        for user_id in range(50):
            name_map[f"user_{user_id}"] = f"qq_{user_id}"

        cache[group_key] = name_map

    # Cache size should never exceed maxsize
    assert len(cache) <= 200


def test_no_nested_container_unbounded_growth():
    """Test that nested containers don't grow unbounded with write-through."""
    cache = BoundedCache(maxsize=5, ttl=None)

    # Create initial entry
    cache["s0"] = []

    # Try to grow with write-through (copy on write)
    for i in range(10000):
        buffer = cache.get("s0", [])
        buffer.append(i)
        # Simulate manual truncation (as in real code)
        if len(buffer) > 100:
            buffer = buffer[-100:]
        cache["s0"] = buffer

    # List should be truncated to 100
    assert len(cache["s0"]) == 100


# ============================================================================
# 3. _touch() Method Tests (3)
# ============================================================================

def test_touch_updates_ttl():
    """Test that _touch() updates TTL timestamp."""
    cache = BoundedCache(maxsize=10, ttl=0.2)
    cache['key'] = []

    initial_timestamp = cache._timestamps['key']
    time.sleep(0.1)

    cache._touch('key')

    assert cache._timestamps['key'] > initial_timestamp


def test_touch_updates_lru():
    """Test that _touch() updates LRU position."""
    cache = BoundedCache(maxsize=3)
    cache['a'] = []
    cache['b'] = []
    cache['c'] = []

    # Touch 'a'
    cache._touch('a')

    # Add new key - should evict 'b', not 'a'
    cache['d'] = []

    assert 'a' in cache
    assert 'b' not in cache


def test_touch_nonexistent_raises():
    """Test that _touch() raises KeyError for non-existent keys."""
    cache = BoundedCache(maxsize=10)

    with pytest.raises(KeyError):
        cache._touch('nonexistent')


# ============================================================================
# 4. Real Usage Simulation (2)
# ============================================================================

def test_real_chat_context_buffer_usage():
    """Simulate real usage pattern from core/main.py line 415-434."""
    cache = BoundedCache(maxsize=200, ttl=7200)

    def add_to_buffer(key, sender, text):
        """Simulate _add_to_chat_context_buffer method."""
        import time as time_module
        buffer = cache.get(key, [])
        buffer.append({
            "sender": sender,
            "text": text,
            "time": time_module.strftime("%H:%M"),
            "images": []
        })
        if len(buffer) > 100:
            buffer = buffer[-100:]
        cache[key] = buffer

    # Simulate multiple sessions
    for i in range(300):
        key = f"group_{i}"
        for j in range(10):
            add_to_buffer(key, f"user_{j}", f"msg {j}")

    # Should stay bounded
    assert len(cache) <= 200

    # Each entry should be truncated
    for key in cache.keys():
        assert len(cache[key]) <= 100


def test_real_name_to_id_usage():
    """Simulate real usage pattern from core/main.py line 635-641."""
    cache = BoundedCache(maxsize=200, ttl=86400)

    def update_name_to_id(group_key, sender_name, sender_id):
        """Simulate name_to_id update."""
        name_map = cache.get(group_key, {})
        name_map[sender_name] = sender_id
        cache[group_key] = name_map

    # Simulate many groups and users
    for group_id in range(300):
        group_key = f"group_{group_id}"
        for user_id in range(20):
            update_name_to_id(
                group_key,
                f"user_{user_id}",
                f"qq_{user_id}"
            )

    # Should stay bounded
    assert len(cache) <= 200
