"""
Unit tests for BoundedCache class.

Tests cover LRU eviction, TTL expiration, thread safety, async safety,
edge cases, and memory bounds for issue #134.
"""

import pytest
import time
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from core.utils.cache import BoundedCache


# ============================================================================
# 1. Basic Tests (3)
# ============================================================================

def test_import_bounded_cache():
    """Test that BoundedCache can be imported successfully."""
    assert BoundedCache is not None


def test_create_with_maxsize():
    """Test creating cache with maxsize parameter."""
    cache = BoundedCache(maxsize=10)
    assert cache is not None


def test_create_with_ttl():
    """Test creating cache with TTL parameter."""
    cache = BoundedCache(maxsize=10, ttl=5.0)
    assert cache is not None


# ============================================================================
# 2. LRU Tests (5)
# ============================================================================

def test_lru_eviction_on_overflow():
    """Test that LRU eviction happens when maxsize is exceeded."""
    cache = BoundedCache(maxsize=3)
    cache['a'] = 1
    cache['b'] = 2
    cache['c'] = 3
    cache['d'] = 4  # Should evict 'a'

    assert 'a' not in cache
    assert 'b' in cache
    assert 'c' in cache
    assert 'd' in cache


def test_lru_access_updates_order():
    """Test that accessing an item updates its LRU position."""
    cache = BoundedCache(maxsize=3)
    cache['a'] = 1
    cache['b'] = 2
    cache['c'] = 3

    _ = cache['a']  # Access 'a', making it most recent
    cache['d'] = 4  # Should evict 'b', not 'a'

    assert 'a' in cache
    assert 'b' not in cache
    assert 'c' in cache
    assert 'd' in cache


def test_lru_update_refreshes_position():
    """Test that updating an item refreshes its LRU position."""
    cache = BoundedCache(maxsize=3)
    cache['a'] = 1
    cache['b'] = 2
    cache['c'] = 3

    cache['a'] = 10  # Update 'a', making it most recent
    cache['d'] = 4   # Should evict 'b', not 'a'

    assert cache['a'] == 10
    assert 'b' not in cache
    assert 'c' in cache
    assert 'd' in cache


def test_lru_maxsize_one():
    """Test LRU behavior with maxsize=1."""
    cache = BoundedCache(maxsize=1)
    cache['a'] = 1
    assert cache['a'] == 1

    cache['b'] = 2  # Should evict 'a'
    assert 'a' not in cache
    assert cache['b'] == 2


def test_lru_get_method():
    """Test that get() method updates LRU position."""
    cache = BoundedCache(maxsize=3)
    cache['a'] = 1
    cache['b'] = 2
    cache['c'] = 3

    value = cache.get('a')  # Access via get()
    assert value == 1

    cache['d'] = 4  # Should evict 'b', not 'a'
    assert 'a' in cache
    assert 'b' not in cache


# ============================================================================
# 3. TTL Tests (6)
# ============================================================================

def test_ttl_expiration():
    """Test that items expire after TTL seconds."""
    cache = BoundedCache(maxsize=10, ttl=0.1)
    cache['key'] = 'value'

    assert cache['key'] == 'value'
    time.sleep(0.15)

    with pytest.raises(KeyError):
        _ = cache['key']


def test_ttl_not_expired():
    """Test that items don't expire before TTL."""
    cache = BoundedCache(maxsize=10, ttl=1.0)
    cache['key'] = 'value'

    time.sleep(0.1)
    assert cache['key'] == 'value'


def test_ttl_zero():
    """Test that TTL=0 means immediate expiration."""
    cache = BoundedCache(maxsize=10, ttl=0)
    cache['key'] = 'value'

    with pytest.raises(KeyError):
        _ = cache['key']


def test_ttl_none_no_expiration():
    """Test that TTL=None means no expiration."""
    cache = BoundedCache(maxsize=10, ttl=None)
    cache['key'] = 'value'

    time.sleep(0.1)
    assert cache['key'] == 'value'


def test_ttl_access_does_not_refresh():
    """Test that accessing an item does not refresh its TTL."""
    cache = BoundedCache(maxsize=10, ttl=0.2)
    cache['key'] = 'value'

    time.sleep(0.1)
    _ = cache['key']  # Access at t=0.1

    time.sleep(0.15)  # Total t=0.25, should be expired
    with pytest.raises(KeyError):
        _ = cache['key']


def test_ttl_update_refreshes():
    """Test that updating an item refreshes its TTL."""
    cache = BoundedCache(maxsize=10, ttl=0.2)
    cache['key'] = 'value1'

    time.sleep(0.1)
    cache['key'] = 'value2'  # Update at t=0.1

    time.sleep(0.15)  # Total t=0.25, but updated at t=0.1
    assert cache['key'] == 'value2'  # Should not be expired


# ============================================================================
# 4. Thread Safety Tests (3)
# ============================================================================

def test_thread_safety_concurrent_writes():
    """Test that concurrent writes from multiple threads are safe."""
    cache = BoundedCache(maxsize=100)

    def writer(thread_id):
        for i in range(100):
            cache[f't{thread_id}_k{i}'] = i

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(writer, tid) for tid in range(10)]
        for future in futures:
            future.result()

    # No assertions - just checking for no crashes/deadlocks


def test_thread_safety_concurrent_read_write():
    """Test concurrent reads and writes from multiple threads."""
    cache = BoundedCache(maxsize=50)

    # Pre-populate
    for i in range(50):
        cache[f'key{i}'] = i

    def reader():
        for i in range(100):
            try:
                _ = cache.get(f'key{i % 50}')
            except KeyError:
                pass

    def writer():
        for i in range(100):
            cache[f'new{i}'] = i

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(reader) for _ in range(2)]
        futures += [executor.submit(writer) for _ in range(2)]
        for future in futures:
            future.result()


def test_thread_safety_eviction_no_race():
    """Test that eviction under concurrent access doesn't cause races."""
    cache = BoundedCache(maxsize=10)
    errors = []

    def accessor(thread_id):
        try:
            for i in range(100):
                cache[f't{thread_id}_{i}'] = i
                _ = cache.get(f't{thread_id}_{i}', None)
        except Exception as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(accessor, tid) for tid in range(5)]
        for future in futures:
            future.result()

    assert len(errors) == 0


# ============================================================================
# 5. Async Safety Tests (1)
# ============================================================================

@pytest.mark.asyncio
async def test_async_concurrent_access():
    """Test that cache works correctly with asyncio concurrent access."""
    cache = BoundedCache(maxsize=50)

    async def writer(coro_id):
        for i in range(50):
            cache[f'c{coro_id}_k{i}'] = i
            await asyncio.sleep(0.001)

    async def reader(coro_id):
        for i in range(50):
            _ = cache.get(f'c{coro_id}_k{i}', None)
            await asyncio.sleep(0.001)

    tasks = []
    for cid in range(5):
        tasks.append(writer(cid))
        tasks.append(reader(cid))

    await asyncio.gather(*tasks)


# ============================================================================
# 6. Edge Cases Tests (10)
# ============================================================================

def test_edge_maxsize_zero_raises():
    """Test that maxsize=0 raises ValueError."""
    with pytest.raises(ValueError):
        BoundedCache(maxsize=0)


def test_edge_negative_maxsize_raises():
    """Test that negative maxsize raises ValueError."""
    with pytest.raises(ValueError):
        BoundedCache(maxsize=-1)


def test_edge_delete_existing():
    """Test deleting an existing key."""
    cache = BoundedCache(maxsize=10)
    cache['key'] = 'value'

    del cache['key']
    assert 'key' not in cache


def test_edge_delete_nonexistent_raises():
    """Test that deleting non-existent key raises KeyError."""
    cache = BoundedCache(maxsize=10)

    with pytest.raises(KeyError):
        del cache['nonexistent']


def test_edge_clear():
    """Test that clear() removes all items."""
    cache = BoundedCache(maxsize=10)
    cache['a'] = 1
    cache['b'] = 2
    cache['c'] = 3

    cache.clear()
    assert len(cache) == 0
    assert 'a' not in cache


def test_edge_len():
    """Test that len() returns correct count."""
    cache = BoundedCache(maxsize=10)
    assert len(cache) == 0

    cache['a'] = 1
    cache['b'] = 2
    assert len(cache) == 2

    del cache['a']
    assert len(cache) == 1


def test_edge_iteration():
    """Test that iteration over cache keys works."""
    cache = BoundedCache(maxsize=10)
    cache['a'] = 1
    cache['b'] = 2
    cache['c'] = 3

    keys = list(cache)
    assert set(keys) == {'a', 'b', 'c'}


def test_edge_none_value():
    """Test that None can be stored as a value."""
    cache = BoundedCache(maxsize=10)
    cache['key'] = None

    assert 'key' in cache
    assert cache['key'] is None


def test_edge_complex_keys():
    """Test that complex keys (tuples) work correctly."""
    cache = BoundedCache(maxsize=10)
    key1 = ('user', 123)
    key2 = ('user', 456)

    cache[key1] = 'alice'
    cache[key2] = 'bob'

    assert cache[key1] == 'alice'
    assert cache[key2] == 'bob'


def test_edge_get_with_default():
    """Test that get() returns default for missing keys."""
    cache = BoundedCache(maxsize=10)

    result = cache.get('nonexistent', 'default')
    assert result == 'default'

    result = cache.get('nonexistent')
    assert result is None


# ============================================================================
# 7. Memory Behavior Tests (2)
# ============================================================================

def test_memory_bounded_growth():
    """Test that cache size never exceeds maxsize."""
    cache = BoundedCache(maxsize=100)

    for i in range(1000):
        cache[f'key{i}'] = 'x' * 100
        assert len(cache) <= 100


def test_memory_ttl_cleanup():
    """Test that expired items are cleaned up and don't accumulate."""
    cache = BoundedCache(maxsize=100, ttl=0.1)

    # Add items
    for i in range(50):
        cache[f'key{i}'] = i

    assert len(cache) == 50

    time.sleep(0.15)

    # Try to access - should all be expired
    valid_count = 0
    for i in range(50):
        if cache.get(f'key{i}') is not None:
            valid_count += 1

    assert valid_count == 0
