"""
Unit tests for Issue #184: per-session lock concurrency behavior

Tests verify the NEW behavior introduced by #171 (replacing the #130 global lock):
1. Parallel execution for different sessions (per-session locks)
2. Serial execution for same session (per-session lock)
3. Semaphore concurrency limit (_session_semaphore)
4. ChatLLM stateless capability detection
5. High concurrency stability
6. Lock acquisition order / overlap across sessions

These tests exercise the real TaleCore._handle_respond_message path with mocked
ChatLLM / adapter bridge (no API keys needed). The typing delay
(calculate_split_interval, simulates human typing per message) is disabled in
the fixture because it is a UX simulation unrelated to concurrency semantics.
"""

import pytest
import asyncio
import time
import threading
from unittest.mock import Mock, AsyncMock, patch
from concurrent.futures import ThreadPoolExecutor

# Import components to test
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.main import TaleCore
from core.adapter.event import PlatformType, EventType
from core.adapter.message_processor import ProcessedMessage, ResponseDecision


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_chatllm():
    """Mock ChatLLM with a blocking chat() call (200ms) and session state"""
    mock = Mock()
    mock.messages = []
    mock.current_sid = None

    def mock_chat(user_input, persist_content=None, save_to_session=True):
        """Simulate blocking LLM call with 200ms delay"""
        time.sleep(0.2)  # Simulate network I/O
        return "<msg><text>Reply OK</text></msg>"

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
    """Create TaleCore instance with mocked dependencies.

    打字延迟（calculate_split_interval，模拟真人逐条打字）与并发语义无关，
    在此统一禁用，避免每条回复被 typing_speed * 字数 拖慢数秒。
    """
    with patch("core.main.calculate_split_interval", return_value=0.0):
        core = TaleCore()
        core.chat = mock_chatllm
        core.toolllm = Mock()
        core.adapter_bridge = mock_adapter_bridge
        core.session_manager = None  # Disable persistence for tests
        core.bridge = None  # 跨会话 bridge 不需要
        core._llm_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="test-llm")

        # Mock message processor
        mock_processor = Mock()
        core.message_processor = mock_processor

        yield core


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


def current_message(user_input: str) -> str:
    """从 user_input 中提取当前用户消息（_handle_respond_message 会组装
    时间/元数据/环境等结构化上下文，当前消息在 '## 当前消息' 段）。"""
    return user_input.rsplit("## 当前消息", 1)[-1].strip()[:30]


# ============================================================================
# Test 1: Parallel execution for different sessions
# ============================================================================

@pytest.mark.asyncio
async def test_parallel_different_sessions(tale_core_with_mocks):
    """
    Test that messages from different sessions execute in parallel.

    Current behavior (#171): per-session locks allow different sessions to
    run concurrently (bounded by _session_semaphore). 3 sessions with a
    200ms chat call should finish in ~200ms, not ~600ms serial.
    """
    core = tale_core_with_mocks

    # Track execution timeline
    execution_log = []
    lock = threading.Lock()

    # Wrap chat method to track timing
    original_chat = core.chat.chat
    def tracked_chat(user_input, persist_content=None, save_to_session=True):
        with lock:
            execution_log.append(("start", current_message(user_input), time.time()))
        result = original_chat(user_input, persist_content, save_to_session)
        with lock:
            execution_log.append(("end", current_message(user_input), time.time()))
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
    # With 200ms per call, 3 parallel calls take ~200ms; serial would take ~600ms
    assert total_time < 0.5, (
        f"Different sessions blocked each other (took {total_time:.2f}s, expected <0.5s). "
        f"Per-session concurrency is broken."
    )

    # All 3 sessions should overlap with each other (per-session locks, not global)
    assert overlaps >= 2, (
        f"Only {overlaps} overlaps detected, expected at least 2. "
        f"Executions are serially blocked by a shared lock."
    )


# ============================================================================
# Test 2: Serial execution for same session
# ============================================================================

@pytest.mark.asyncio
async def test_serial_same_session(tale_core_with_mocks):
    """
    Test that messages from the same session execute serially in order.

    Current behavior (#171): the per-session lock guarantees strict ordering
    within one session. Two 200ms calls take ~400ms (serial), and the second
    call starts only after the first finishes.
    """
    core = tale_core_with_mocks

    execution_log = []
    lock = threading.Lock()

    # Track execution with message content
    original_chat = core.chat.chat
    def tracked_chat(user_input, persist_content=None, save_to_session=True):
        with lock:
            execution_log.append(("start", current_message(user_input), time.time()))
        result = original_chat(user_input, persist_content, save_to_session)
        with lock:
            execution_log.append(("end", current_message(user_input), time.time()))
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

    # Total time should be ~400ms (2 * 200ms serial); if the per-session lock
    # is broken and they run concurrently, total would be ~200ms and this fails.
    assert 0.35 < total_time < 0.65, (
        f"Execution time {total_time:.2f}s unexpected for serial execution"
    )

    print(f"\nOK: Same session messages executed serially (gap: {(start2_time - end1_time) * 1000:.1f}ms)")


# ============================================================================
# Test 3: Semaphore concurrency limit
# ============================================================================

@pytest.mark.asyncio
async def test_semaphore_limit(tale_core_with_mocks):
    """
    Test that _session_semaphore(3) limits concurrent executions to 3.

    Current behavior (#171): different sessions run in parallel (per-session
    locks) but global concurrency is capped at 3. 10 tasks with 200ms each
    take ~4 waves = ~800ms, and at most 3 chats run simultaneously.
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
    print(f"Expected time with Semaphore(3): ~0.8s (10 tasks / 3 = 4 waves * 0.2s)")
    print(f"Expected time without rate limit: ~0.2s (all 10 at once)")

    # At most 3 concurrent chats (semaphore enforces the cap)
    assert max_active <= 3, (
        f"Max concurrent executions was {max_active}, expected <= 3. "
        f"The semaphore limit is not enforced."
    )

    # At least 3 concurrent chats (per-session locks allow real parallelism)
    assert max_active >= 3, (
        f"Max concurrent executions was {max_active}, expected >= 3. "
        f"Executions are serialized (global lock regression?)."
    )

    # With Semaphore(3) and 200ms calls, 10 tasks take ~4 waves (~0.8s).
    # Without rate limiting it would be ~0.2s; with a global lock ~2.0s.
    assert 0.5 < total_time < 1.5, (
        f"Execution took {total_time:.2f}s, expected 0.5-1.5s with Semaphore(3). "
        f"Rate limiting or concurrency is broken."
    )


# ============================================================================
# Test 4: ChatLLM stateless capability
# ============================================================================

@pytest.mark.asyncio
async def test_chatllm_stateless(tale_core_with_mocks):
    """
    Test stateless ChatLLM capability detection and per-session isolation.

    Current behavior (#171): TaleCore detects whether chat() supports the
    stateless signature (sid=/messages= parameters). The hot path still goes
    through set_session() under the per-session lock, so different sessions
    must never observe each other's input.
    """
    core = tale_core_with_mocks

    # 1. Old interface (chat without sid/messages params) is detected as stateful
    assert core._check_chatllm_stateless() is False, (
        "Old-style chat() without sid/messages should be detected as stateful"
    )

    # 2. New stateless interface (chat with sid/messages params) is detected
    recorded_calls = []
    recorded_sids = []

    def stateless_chat_call(user_input, persist_content=None, save_to_session=True,
                            sid=None, messages=None):
        recorded_calls.append((current_message(user_input), sid, messages))
        time.sleep(0.05)
        return "<msg><text>Stateless OK</text></msg>"

    def stateless_set_session(sid, load_history=True):
        recorded_sids.append(sid)
        stateless_chat.current_sid = sid

    stateless_chat = Mock()
    stateless_chat.chat = stateless_chat_call
    stateless_chat.set_session = stateless_set_session
    stateless_chat._save_session_memory = Mock()

    core.chat = stateless_chat

    assert core._check_chatllm_stateless() is True, (
        "chat(sid=..., messages=...) should be detected as stateless"
    )

    # 3. Two different sessions: no cross-contamination of input, correct sids
    msg1 = create_test_message("group_stateless_a", "Msg A")
    msg2 = create_test_message("group_stateless_b", "Msg B")

    await core._handle_respond_message(msg1, adapter_instance="qq")
    await core._handle_respond_message(msg2, adapter_instance="qq")

    print(f"\n=== Stateless Test Results ===")
    print(f"Recorded calls: {recorded_calls}")
    print(f"Recorded sids: {recorded_sids}")

    assert len(recorded_calls) == 2, (
        f"Expected 2 chat calls, got {len(recorded_calls)}"
    )
    # Each call receives its own session's message - no cross-contamination
    assert recorded_calls[0][0] == "Msg A", (
        f"First call got {recorded_calls[0][0]!r}, expected 'Msg A'"
    )
    assert recorded_calls[1][0] == "Msg B", (
        f"Second call got {recorded_calls[1][0]!r}, expected 'Msg B'"
    )
    # set_session is invoked with the correct per-session sid
    assert recorded_sids == ["qq:gm:group_stateless_a", "qq:gm:group_stateless_b"], (
        f"set_session sids {recorded_sids} do not match expected sessions"
    )


# ============================================================================
# Test 5: High concurrency stability
# ============================================================================

@pytest.mark.asyncio
async def test_high_concurrency_stability(tale_core_with_mocks):
    """
    Test system stability under high concurrent load (50 requests).

    Current behavior: 50 requests across 10 sessions, semaphore caps at 3
    concurrent; with 50ms per call this completes in ~1s. Validates no
    deadlocks (timeout watchdog), no cross-session corruption.
    """
    core = tale_core_with_mocks

    # Reduce mock delay for faster test execution
    original_chat = core.chat.chat
    def fast_chat(user_input, persist_content=None, save_to_session=True):
        time.sleep(0.05)  # 50ms instead of 200ms
        return "<msg><text>Reply</text></msg>"

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

    # With Semaphore(3) and 50ms per call: 50 / 3 = ~17 waves * 50ms = ~0.85s.
    # Allow up to 3s for overhead.
    assert total_time < 3.0, (
        f"High concurrency took {total_time:.2f}s, expected <3.0s. "
        f"Performance degradation detected."
    )

    print(f"\nOK: High concurrency test passed in {total_time:.2f}s")


# ============================================================================
# Additional Test: Lock acquisition order
# ============================================================================

@pytest.mark.asyncio
async def test_lock_acquisition_order(tale_core_with_mocks):
    """
    Test that per-session locks are acquired independently and don't cause
    deadlocks.

    Current behavior (#171): each session has its own lock; interleaved
    requests from sessions A and B must show overlapping lock holds.
    """
    core = tale_core_with_mocks

    # Track lock acquisition
    lock_events = []
    lock = threading.Lock()

    original_chat = core.chat.chat
    def tracked_chat(user_input, persist_content=None, save_to_session=True):
        with lock:
            lock_events.append(("acquire", current_message(user_input), time.time()))

        result = original_chat(user_input, persist_content, save_to_session)

        with lock:
            lock_events.append(("release", current_message(user_input), time.time()))

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

            if msg_i == msg_j:
                continue  # 同会话本来就串行，不参与跨会话重叠判断

            # Find release times
            rel_i = next(t for m, t in release_times if m == msg_i and t > acq_i)
            rel_j = next(t for m, t in release_times if m == msg_j and t > acq_j)

            # Check overlap
            if acq_i < rel_j and acq_j < rel_i:
                has_overlap = True
                print(f"\nOK: Overlap detected: {msg_i} and {msg_j}")
                break

    # With per-session locks, different sessions should overlap
    assert has_overlap, (
        "No lock overlaps detected. Different sessions are serialized "
        "(shared lock regression?)."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
