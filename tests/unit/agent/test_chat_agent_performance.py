"""
Integration tests for ChatAgent performance benchmarks

These tests verify actual performance numbers and prove the fix works.
"""
import pytest
import asyncio
import time
from typing import List, Dict
from unittest.mock import AsyncMock

from core.agent import ChatAgent


@pytest.fixture
def mock_llm_provider_benchmark():
    """Mock LLM provider with realistic timing"""
    provider = AsyncMock()

    async def mock_chat(messages, model=None, timeout=None):
        """Simulate realistic LLM call (0.5s)"""
        await asyncio.sleep(0.5)
        last_user_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), 'unknown')
        return f"Response to: {last_user_msg}"

    provider.chat = mock_chat
    return provider


class TestChatAgentPerformance:
    """Performance benchmarks to verify concurrency fix (CRITICAL)"""

    @pytest.mark.asyncio
    async def test_benchmark_3_concurrent_users(self, mock_llm_provider_benchmark):
        """
        PERFORMANCE BENCHMARK: 3 concurrent users

        Setup: 3 different users, each sends 1 message
        LLM latency: 0.5s per call
        Expected: ~0.5s total (concurrent)
        Failure: ~1.5s total (serial, indicates broken concurrency)

        This is the KEY test proving global lock is removed
        """
        agent = ChatAgent(mock_llm_provider_benchmark)
        start_time = time.time()

        # 3 concurrent calls, different sessions
        tasks = [
            agent.generate(
                messages=[{"role": "user", "content": f"User {i}"}],
                session_id=f"user{i}",
                timeout=60.0
            )
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        # Performance target: <0.8s (concurrent)
        assert elapsed < 0.8, f"3 concurrent users took {elapsed:.2f}s, expected <0.8s (CONCURRENCY BROKEN)"
        assert len(results) == 3

        # Record benchmark result
        print(f"\nBENCHMARK: 3 concurrent users completed in {elapsed:.2f}s")

    @pytest.mark.asyncio
    async def test_benchmark_same_user_sequential(self, mock_llm_provider_benchmark):
        """
        PERFORMANCE BENCHMARK: Same user, 3 sequential messages

        Setup: 1 user sends 3 messages in sequence
        LLM latency: 0.5s per call
        Expected: ~1.5s total (serial)

        Verifies per-session lock maintains message order
        """
        agent = ChatAgent(mock_llm_provider_benchmark)
        start_time = time.time()

        # 3 sequential calls, same session
        for i in range(3):
            await agent.generate(
                messages=[{"role": "user", "content": f"Message {i}"}],
                session_id="user1",
                timeout=60.0
            )

        elapsed = time.time() - start_time

        # Performance target: ≥1.4s and <1.8s (serial)
        assert elapsed >= 1.4, f"Sequential took {elapsed:.2f}s, expected ≥1.4s"
        assert elapsed < 1.8, f"Sequential took {elapsed:.2f}s, expected <1.8s"

        print(f"\nBENCHMARK: Same user 3 messages completed in {elapsed:.2f}s")

    @pytest.mark.asyncio
    async def test_benchmark_5_users_with_semaphore(self, mock_llm_provider_benchmark):
        """
        PERFORMANCE BENCHMARK: 5 concurrent users with Semaphore(3)

        Setup: 5 different users, max 3 concurrent
        LLM latency: 0.5s per call
        Expected: ~1.0s total (two waves: 3 + 2)
        Failure: ~2.5s total (fully serial)

        Verifies semaphore rate limiting works correctly
        """
        agent = ChatAgent(mock_llm_provider_benchmark, max_concurrency=3)
        start_time = time.time()

        # 5 concurrent calls, max 3 concurrent due to semaphore
        tasks = [
            agent.generate(
                messages=[{"role": "user", "content": f"User {i}"}],
                session_id=f"user{i}",
                timeout=60.0
            )
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        # Performance target: ≥0.9s (two waves) and <1.3s
        assert elapsed >= 0.9, f"5 users took {elapsed:.2f}s, expected ≥0.9s"
        assert elapsed < 1.3, f"5 users took {elapsed:.2f}s, expected <1.3s (SEMAPHORE BROKEN)"
        assert len(results) == 5

        print(f"\nBENCHMARK: 5 users with semaphore completed in {elapsed:.2f}s")

    @pytest.mark.asyncio
    async def test_benchmark_mixed_workload(self, mock_llm_provider_benchmark):
        """
        REALISTIC WORKLOAD: Mix of concurrent and sequential

        Setup:
        - User1: Sends 3 messages sequentially
        - User2: Sends 2 messages sequentially
        - User3: Sends 1 message
        All start at the same time

        Expected timeline:
        t=0.0s: User1-Msg1, User2-Msg1, User3-Msg1 start (3 concurrent)
        t=0.5s: All 3 complete, User1-Msg2, User2-Msg2 start (2 concurrent)
        t=1.0s: Both complete, User1-Msg3 starts (1 concurrent)
        t=1.5s: User1-Msg3 completes
        Total: ~1.5s

        Verifies both per-session serial and cross-session concurrent work together
        """
        agent = ChatAgent(mock_llm_provider_benchmark)
        start_time = time.time()

        async def user1_workflow():
            for i in range(3):
                await agent.generate(
                    messages=[{"role": "user", "content": f"User1-Msg{i}"}],
                    session_id="user1",
                    timeout=60.0
                )

        async def user2_workflow():
            for i in range(2):
                await agent.generate(
                    messages=[{"role": "user", "content": f"User2-Msg{i}"}],
                    session_id="user2",
                    timeout=60.0
                )

        async def user3_workflow():
            await agent.generate(
                messages=[{"role": "user", "content": "User3-Msg0"}],
                session_id="user3",
                timeout=60.0
            )

        await asyncio.gather(user1_workflow(), user2_workflow(), user3_workflow())

        elapsed = time.time() - start_time

        # Performance target: ≥1.4s and <1.8s
        assert elapsed >= 1.4, f"Mixed workload took {elapsed:.2f}s, expected ≥1.4s"
        assert elapsed < 1.8, f"Mixed workload took {elapsed:.2f}s, expected <1.8s"

        print(f"\nBENCHMARK: Mixed workload completed in {elapsed:.2f}s")

    @pytest.mark.asyncio
    async def test_stress_10_concurrent_users(self, mock_llm_provider_benchmark):
        """
        STRESS TEST: 10 concurrent users with Semaphore(3)

        Setup: 10 different users, max 3 concurrent
        LLM latency: 0.5s per call
        Expected: ~2.0s total (4 waves: 3+3+3+1)

        Verifies system stability under higher load
        """
        agent = ChatAgent(mock_llm_provider_benchmark, max_concurrency=3)
        start_time = time.time()

        # 10 concurrent calls, max 3 concurrent
        tasks = [
            agent.generate(
                messages=[{"role": "user", "content": f"User {i}"}],
                session_id=f"user{i}",
                timeout=60.0
            )
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)

        elapsed = time.time() - start_time

        # Performance target: ≥1.8s (4 waves) and <2.5s
        assert elapsed >= 1.8, f"10 users took {elapsed:.2f}s, expected ≥1.8s"
        assert elapsed < 2.5, f"10 users took {elapsed:.2f}s, expected <2.5s"
        assert len(results) == 10

        print(f"\nSTRESS TEST: 10 concurrent users completed in {elapsed:.2f}s")
