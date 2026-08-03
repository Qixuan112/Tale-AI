"""
Unit tests for Issue #130: Global lock concurrency problem

Tests cover:
1. Parallel execution for different sessions
2. Serial execution for same session
3. Semaphore concurrency limit
4. ChatLLM stateless verification
5. High concurrency stability

These tests MUST FAIL before the fix is applied, validating that the current
implementation indeed has the global lock problem where all sessions block each other.
"""

import pytest
import asyncio
import time
import threading
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Import components to test
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.main import TaleCore
from core.adapter.event import (
    PlatformEvent, PlatformType, EventType,
    SenderInfo, MessageContent
)
from core.adapter.message_processor import ProcessedMessage, ResponseDecision


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_chatllm():
    """Mock ChatLLM with stateful behavior (simulating current implementation)"""
    mock = Mock()
    mock.messages = []
    mock.current_sid = None

    def mock_chat(user_input, persist_content=None, save_to_session=True):
        """Simulate blocking LLM call with 200ms delay"""
        time.sleep(0.2)  # Simulate network I/O
        return f"<msg><text>Reply to: {user_input[:50]}</text></msg>"

    def mock_set_session(sid, load_history=True):
        """Simulate session state mutation"""
        mock.current_sid = sid
        mock.messages = [{"role": "system", "content": "You are Tale AI"}]

    mock.chat = mock_chat
    mock.set_session = mock_set_session
    mock._save_session_memory = Mock()

    return mock


@pytest.fixture
def mock_adapter_bridge():
    """Mock adapter bridge for message sending"""
    mock = AsyncMock()

    async def mock_send_message(*args, **kwargs):
        await asyncio.sleep(0.01)  # Minimal delay
        from core.adapter.event import SendResult
        return SendResult(success=True, failed_files=[])

    mock.send_message = mock_send_message
    return mock


@pytest.fixture
def tale_core_with_mocks(mock_chatllm, mock_adapter_bridge):
    """Create TaleCore instance with mocked dependencies"""
    core = TaleCore()
    core.chat = mock_chatllm
    core.toolllm = Mock()
    core.adapter_bridge = mock_adapter_bridge
    core.session_manager = None  # Disable persistence for tests
    core._llm_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="test-llm")

    # Mock message processor
    mock_processor = Mock()
    core.message_processor = mock_processor

    return core


def create_test_message(session_id: str, text: str, is_group: bool = True) -> ProcessedMessage:
    """Helper to create ProcessedMessage for testing"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.GROUP_MESSAGE if is_group else EventType.PRIVATE_MESSAGE,
        message_id=f"msg_{int(time.time() * 1000000)}",
        sender_id=f"user_{session_id}",
        sender_name=f"User {session_id}",
        is_bot=False,
        text=text,
        images=[],
        group_id=session_id if is_group else None,
        group_name=f"Group {session_id}" if is_group else None,
        decision=ResponseDecision.RESPOND,
        reason="test message"
    )


# ============================================================================
# Test 1: Parallel execution for different sessions
# ============================================================================

@pytest.mark.asyncio
async def test_parallel_different_sessions(tale_core_with_mocks):
    """
    Test that messages from different sessions can execute in parallel.

    **Expected behavior after fix**: 3 sessions execute concurrently with overlapping timestamps.
    **Current behavior (SHOULD FAIL)**: Global lock forces serial execution, no overlap.

    This test validates that the global lock problem exists before the fix.
    """
    core = tale_core_with_mocks

    # Track execution timeline
    execution_log = []
    lock = threading.Lock()

    # Wrap chat method to track timing
    original_chat = core.chat.chat
    def tracked_chat(user_input, persist_content=None, save_to_session=True):
        with lock:
            execution_log.append(("start", user_input[:20], time.time()))
        result = original_chat(user_input, persist_content, save_to_session)
        with lock:
            execution_log.append(("end", user_input[:20], time.time()))
        return result

    core.chat.chat = tracked_chat

    # Create messages for 3 different sessions
    messages = [
        create_test_message("group_A", "Hello from A"),
        create_test_message("group_B", "Hello from B"),
        create_test_message("group_C", "Hello from C"),
    ]

    # Execute all messages concurrently
    start_time = time.time()
    tasks = [
        core._handle_respond_message(msg, adapter_instance="qq")
        for msg in messages
    ]
    await asyncio.gather(*tasks)
    total_time = time.time() - start_time

    # Analyze execution timeline
    print(f"\n=== Execution Timeline (test_parallel_different_sessions) ===")
    for event_type, msg_prefix, timestamp in execution_log:
        rel_time = (timestamp - start_time) * 1000
        print(f"  [{rel_time:6.1f}ms] {event_type:5s} - {msg_prefix}")

    # Check for parallel execution
    start_times = [t for event, msg, t in execution_log if event == "start"]
    end_times = [t for event, msg, t in execution_log if event == "end"]

    # Verify all started within a short window (parallel dispatch)
    time_window = max(start_times) - min(start_times)
    print(f"\nStart time window: {time_window * 1000:.1f}ms")

    # Calculate overlaps
    overlaps = 0
    for i in range(len(start_times)):
        for j in range(i + 1, len(start_times)):
            # Check if task i and j overlap
            if start_times[i] < end_times[j] and start_times[j] < end_times[i]:
                overlaps += 1

    print(f"Overlapping executions: {overlaps} out of 3 possible")
    print(f"Total execution time: {total_time * 1000:.1f}ms")

    # ASSERTION: Different sessions should execute in parallel
    # With 200ms per call, 3 parallel calls should take ~200ms total
    # Serial execution would take ~600ms
    # Current implementation SHOULD FAIL this assertion (takes ~600ms)
    assert total_time < 0.35, (
        f"Different sessions blocked each other (took {total_time:.2f}s, expected <0.35s). "
        f"This confirms the global lock problem exists."
    )

    # At least 2 sessions should have overlapping execution
    assert overlaps >= 2, (
        f"Only {overlaps} overlaps detected, expected at least 2. "
        f"This confirms sessions are executing serially due to global lock."
    )


# ============================================================================
# Test 2: Serial execution for same session
# ============================================================================

@pytest.mark.asyncio
async def test_serial_same_session(tale_core_with_mocks):
    """
    Test that messages from the same session execute serially in order.

    **Expected behavior**: Second message starts only after first completes.
    **This should PASS both before and after the fix** (per-session lock).
    """
    core = tale_core_with_mocks

    execution_log = []
    lock = threading.Lock()

    # Track execution with message content
    original_chat = core.chat.chat
    def tracked_chat(user_input, persist_content=None, save_to_session=True):
        with lock:
            execution_log.append(("start", user_input[:30], time.time()))
        result = original_chat(user_input, persist_content, save_to_session)
        with lock:
            execution_log.append(("end", user_input[:30], time.time()))
        return result

    core.chat.chat = tracked_chat

    # Two messages from the same session
    session_id = "group_same"
    msg1 = create_test_message(session_id, "First message")
    msg2 = create_test_message(session_id, "Second message")

    # Execute concurrently (but should serialize automatically)
    start_time = time.time()
    tasks = [
        core._handle_respond_message(msg1, adapter_instance="qq"),
        core._handle_respond_message(msg2, adapter_instance="qq"),
    ]
    await asyncio.gather(*tasks)
    total_time = time.time() - start_time

    # Analyze timeline
    print(f"\n=== Execution Timeline (test_serial_same_session) ===")
    for event_type, msg_prefix, timestamp in execution_log:
        rel_time = (timestamp - start_time) * 1000
        print(f"  [{rel_time:6.1f}ms] {event_type:5s} - {msg_prefix}")

    # Verify serial execution
    assert len(execution_log) == 4, f"Expected 4 events, got {len(execution_log)}"

    start1_time = execution_log[0][2]
    end1_time = execution_log[1][2]
    start2_time = execution_log[2][2]
    end2_time = execution_log[3][2]

    # Second message should start AFTER first message ends
    assert start2_time >= end1_time, (
        f"Second message started before first ended! "
        f"start2={start2_time:.3f}, end1={end1_time:.3f}"
    )

    # Total time should be ~400ms (2 * 200ms serial)
    assert 0.35 < total_time < 0.50, (
        f"Execution time {total_time:.2f}s unexpected for serial execution"
    )

    print(f"\n✓ Same session messages executed serially (gap: {(start2_time - end1_time) * 1000:.1f}ms)")


# ============================================================================
# Test 3: Semaphore concurrency limit
# ============================================================================

@pytest.mark.asyncio
async def test_semaphore_limit(tale_core_with_mocks):
    """
    Test that Semaphore(3) limits concurrent executions to 3.

    **Expected behavior after fix**: At most 3 tasks execute concurrently.
    **Current behavior (SHOULD FAIL)**: Global lock limits to 1 concurrent task.

    This test will fail before the fix because only 1 task runs at a time.
    """
    core = tale_core_with_mocks

    # Track active task count over time
    active_count = 0
    max_active = 0
    lock = threading.Lock()

    original_chat = core.chat.chat
    def tracked_chat(user_input, persist_content=None, save_to_session=True):
        nonlocal active_count, max_active

        with lock:
            active_count += 1
            max_active = max(max_active, active_count)

        try:
            result = original_chat(user_input, persist_content, save_to_session)
            return result
        finally:
            with lock:
                active_count -= 1

    core.chat.chat = tracked_chat

    # Create 10 messages from different sessions
    messages = [
        create_test_message(f"group_{i}", f"Message {i}")
        for i in range(10)
    ]

    # Execute all concurrently
    start_time = time.time()
    tasks = [
        core._handle_respond_message(msg, adapter_instance="qq")
        for msg in messages
    ]
    await asyncio.gather(*tasks)
    total_time = time.time() - start_time

    print(f"\n=== Semaphore Test Results ===")
    print(f"Max concurrent executions: {max_active}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Expected time with Semaphore(3): ~0.7s (10 tasks / 3 = 4 batches * 0.2s)")
    print(f"Expected time with global lock: ~2.0s (10 tasks * 0.2s serial)")

    # ASSERTION: With Semaphore(3), max concurrent should be 3
    # Current implementation SHOULD FAIL this (max_active == 1 due to global lock)
    assert max_active >= 3, (
        f"Max concurrent executions was {max_active}, expected >= 3. "
        f"This confirms the global lock prevents parallel execution."
    )

    # With Semaphore(3), 10 tasks should complete in ~0.7-0.8s
    # With global lock, it takes ~2.0s
    assert total_time < 1.0, (
        f"Execution took {total_time:.2f}s, expected <1.0s with Semaphore(3). "
        f"This confirms the global lock serializes all requests."
    )


# ============================================================================
# Test 4: ChatLLM stateless verification
# ============================================================================

@pytest.mark.asyncio
async def test_chatllm_stateless(tale_core_with_mocks):
    """
    Test that ChatLLM.chat() does not mutate instance state.

    **Expected behavior after fix**: chat() is pure function, no state mutation.
    **Current behavior (SHOULD FAIL)**: self.messages and self.current_sid change.

    This test verifies the stateless refactoring goal.
    """
    core = tale_core_with_mocks
    chatllm = core.chat

    # Record initial state
    initial_messages = chatllm.messages.copy() if hasattr(chatllm, 'messages') else None
    initial_sid = chatllm.current_sid if hasattr(chatllm, 'current_sid') else None

    print(f"\n=== ChatLLM State Before Call ===")
    print(f"messages: {initial_messages}")
    print(f"current_sid: {initial_sid}")

    # Make two calls with different sessions
    msg1 = create_test_message("group_X", "Test message 1")
    msg2 = create_test_message("group_Y", "Test message 2")

    await core._handle_respond_message(msg1, adapter_instance="qq")

    # Record state after first call
    mid_messages = chatllm.messages.copy() if hasattr(chatllm, 'messages') else None
    mid_sid = chatllm.current_sid if hasattr(chatllm, 'current_sid') else None

    print(f"\n=== ChatLLM State After First Call ===")
    print(f"messages: {mid_messages}")
    print(f"current_sid: {mid_sid}")

    await core._handle_respond_message(msg2, adapter_instance="qq")

    # Record state after second call
    final_messages = chatllm.messages.copy() if hasattr(chatllm, 'messages') else None
    final_sid = chatllm.current_sid if hasattr(chatllm, 'current_sid') else None

    print(f"\n=== ChatLLM State After Second Call ===")
    print(f"messages: {final_messages}")
    print(f"current_sid: {final_sid}")

    # ASSERTION: For stateless ChatLLM, these should not exist or not change
    # Current implementation SHOULD FAIL this (state mutates)
    if hasattr(chatllm, 'messages'):
        # State exists - check if it pollutes across calls
        assert mid_messages == initial_messages, (
            "ChatLLM.messages was mutated by first call. "
            "This confirms ChatLLM is stateful and needs refactoring."
        )

    if hasattr(chatllm, 'current_sid'):
        # current_sid exists - it should not persist across different sessions
        assert mid_sid == initial_sid, (
            f"ChatLLM.current_sid changed from {initial_sid} to {mid_sid}. "
            f"This confirms ChatLLM maintains session state."
        )


# ============================================================================
# Test 5: High concurrency stability
# ============================================================================

@pytest.mark.asyncio
async def test_high_concurrency_stability(tale_core_with_mocks):
    """
    Test system stability under high concurrent load (50 requests).

    **Expected behavior**: All requests complete successfully within reasonable time.
    **Validates**: No deadlocks, no OOM, performance acceptable.
    """
    core = tale_core_with_mocks

    # Reduce mock delay for faster test execution
    original_chat = core.chat.chat
    def fast_chat(user_input, persist_content=None, save_to_session=True):
        time.sleep(0.05)  # 50ms instead of 200ms
        return f"<msg><text>Reply</text></msg>"

    core.chat.chat = fast_chat

    # Create 50 requests with random sessions (10 unique sessions)
    import random
    messages = [
        create_test_message(f"group_{random.randint(1, 10)}", f"Message {i}")
        for i in range(50)
    ]

    # Execute with timeout to detect deadlocks
    start_time = time.time()
    try:
        tasks = [
            core._handle_respond_message(msg, adapter_instance="qq")
            for msg in messages
        ]
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=30.0)
        total_time = time.time() - start_time
        success = True
    except asyncio.TimeoutError:
        total_time = time.time() - start_time
        success = False

    print(f"\n=== High Concurrency Test Results ===")
    print(f"Total requests: 50")
    print(f"Completed: {success}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average time per request: {total_time / 50 * 1000:.1f}ms")

    # ASSERTIONS
    assert success, "Timeout detected - possible deadlock or extreme slowdown"

    # With Semaphore(3) and 50ms per call, expected time:
    # 50 requests / 3 concurrent = ~17 batches * 50ms = ~0.85s
    # Allow up to 3s for overhead
    assert total_time < 3.0, (
        f"High concurrency took {total_time:.2f}s, expected <3.0s. "
        f"Performance degradation detected."
    )

    # With global lock, would take 50 * 50ms = 2.5s minimum
    # This test helps identify if parallel execution is working
    print(f"\n✓ High concurrency test passed in {total_time:.2f}s")


# ============================================================================
# Additional Test: Lock acquisition order
# ============================================================================

@pytest.mark.asyncio
async def test_lock_acquisition_order(tale_core_with_mocks):
    """
    Test that per-session locks are acquired correctly and don't cause deadlocks.

    **Expected behavior after fix**: Each session has independent lock, no blocking.
    **Current behavior**: Single global lock causes all sessions to wait.
    """
    core = tale_core_with_mocks

    # Track lock acquisition
    lock_events = []
    lock = threading.Lock()

    original_chat = core.chat.chat
    def tracked_chat(user_input, persist_content=None, save_to_session=True):
        with lock:
            lock_events.append(("acquire", user_input[:20], time.time()))

        result = original_chat(user_input, persist_content, save_to_session)

        with lock:
            lock_events.append(("release", user_input[:20], time.time()))

        return result

    core.chat.chat = tracked_chat

    # Interleave requests from 2 sessions: A, B, A, B
    messages = [
        create_test_message("group_A", "A1"),
        create_test_message("group_B", "B1"),
        create_test_message("group_A", "A2"),
        create_test_message("group_B", "B2"),
    ]

    start_time = time.time()
    tasks = [
        core._handle_respond_message(msg, adapter_instance="qq")
        for msg in messages
    ]
    await asyncio.gather(*tasks)

    print(f"\n=== Lock Acquisition Order ===")
    for event_type, msg_id, timestamp in lock_events:
        rel_time = (timestamp - start_time) * 1000
        print(f"  [{rel_time:6.1f}ms] {event_type:7s} - {msg_id}")

    # With per-session locks, A1 and B1 can acquire locks simultaneously
    # Check if any acquires overlap (indicating independent locks)
    acquire_times = [(msg, t) for evt, msg, t in lock_events if evt == "acquire"]
    release_times = [(msg, t) for evt, msg, t in lock_events if evt == "release"]

    # Find if any two different sessions have overlapping lock holds
    has_overlap = False
    for i in range(len(acquire_times)):
        for j in range(i + 1, len(acquire_times)):
            msg_i, acq_i = acquire_times[i]
            msg_j, acq_j = acquire_times[j]

            # Find release times
            rel_i = next(t for m, t in release_times if m == msg_i and t > acq_i)
            rel_j = next(t for m, t in release_times if m == msg_j and t > acq_j)

            # Check overlap
            if acq_i < rel_j and acq_j < rel_i:
                has_overlap = True
                print(f"\n✓ Overlap detected: {msg_i} and {msg_j}")
                break

    # With per-session locks, different sessions should overlap
    # With global lock, NO overlaps (SHOULD FAIL before fix)
    assert has_overlap, (
        "No lock overlaps detected. This confirms the global lock serializes all requests."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
