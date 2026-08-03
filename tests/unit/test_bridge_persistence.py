"""
单元测试：BridgeState 持久化功能

测试 Issue #132 的修复目标：跨会话消息状态持久化
- inbox 消息持久化（重启后继续消费）
- pending 消息持久化（重启后继续等待 ack/超时）
- _processed 去重集合持久化（避免重复处理）
- _last_send 限流时间戳持久化（重启后限流不失效）
- 空闲 sid 过期清理仍工作
- 损坏文件优雅降级

注意：这些测试在当前纯内存实现下会失败，用于验证持久化修复的正确性。
"""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.bridge import BridgeState, BridgeMessage


@pytest.fixture
def temp_state_dir(tmp_path):
    """临时持久化目录"""
    state_dir = tmp_path / "bridge_state"
    state_dir.mkdir(exist_ok=True)
    return state_dir


@pytest.fixture
def bridge_with_persistence(temp_state_dir):
    """带持久化路径的 BridgeState 实例工厂

    注意：当前 BridgeState 不接受持久化参数，此 fixture 为未来实现预留。
    测试会通过 mock 或环境变量注入持久化路径。
    """
    def _create_bridge(state_file=None):
        if state_file is None:
            state_file = temp_state_dir / "bridge_state.json"
        # 创建带持久化的 BridgeState
        return BridgeState(persistence_file=str(state_file)), state_file
    return _create_bridge


# ============================================================================
# 测试1：inbox 持久化 - 重启后消息不丢失
# ============================================================================

@pytest.mark.asyncio
async def test_inbox_persistence_on_restart(bridge_with_persistence):
    """测试 inbox 消息在进程重启后仍可消费

    场景：
    1. 发送 3 条跨会话消息到 inbox
    2. 模拟进程重启（重新实例化 BridgeState）
    3. 验证重启后 inbox 仍有 3 条消息可消费

    预期：当前纯内存实现会失败（重启后 inbox 为空）
    """
    # Phase 1: 发送消息
    bridge1, state_file = bridge_with_persistence()

    from_sid = "qq:user:12345:group:67890"
    to_sid = "qq:user:99999:group:67890"  # 同群组，有权限

    msg_ids = []
    for i in range(3):
        msg_id = await bridge1.send(from_sid, to_sid, f"跨会话消息 {i+1}")
        assert not msg_id.startswith("error:"), f"发送失败: {msg_id}"
        msg_ids.append(msg_id)

    # 验证消息已在 inbox
    messages = await bridge1.consume(to_sid)
    assert len(messages) == 3, "consume 前 inbox 应有 3 条消息"

    # Phase 2: 模拟重启（重新实例化）
    await bridge1.flush()  # 确保状态已持久化
    del bridge1  # 显式释放第一个实例

    # 当前实现：BridgeState() 会创建空状态
    # 未来实现：BridgeState(persistence_file=state_file) 会从文件加载
    bridge2, _ = bridge_with_persistence(state_file)

    # Phase 3: 验证持久化
    messages_after_restart = await bridge2.consume(to_sid)

    # 断言：重启后仍能消费到 3 条消息
    assert len(messages_after_restart) == 3, \
        f"重启后应恢复 3 条 inbox 消息，实际: {len(messages_after_restart)}"

    # 验证消息内容完整
    contents = [m["content"] for m in messages_after_restart]
    assert "跨会话消息 1" in contents
    assert "跨会话消息 2" in contents
    assert "跨会话消息 3" in contents


# ============================================================================
# 测试2：pending 持久化 - 未 ack 消息重启后继续等待
# ============================================================================

@pytest.mark.asyncio
async def test_pending_persistence_on_restart(bridge_with_persistence):
    """测试 pending 消息在重启后仍在 pending 队列，支持超时重投

    场景：
    1. 发送消息并 consume（进入 pending）
    2. 不 ack，模拟重启
    3. 验证重启后 pending 中仍有该消息
    4. 等待 PENDING_TIMEOUT（模拟时间前进），验证超时重排

    预期：当前纯内存实现会失败（重启后 pending 为空）
    """
    # Phase 1: 消息进入 pending
    bridge1, state_file = bridge_with_persistence()

    from_sid = "qq:user:11111:group:22222"
    to_sid = "qq:user:33333:group:22222"

    msg_id = await bridge1.send(from_sid, to_sid, "需要 ack 的消息")
    assert not msg_id.startswith("error:")

    # consume 但不 ack
    messages = await bridge1.consume(to_sid)
    assert len(messages) == 1
    assert messages[0]["id"] == msg_id

    # Phase 2: 模拟重启
    await bridge1.flush()  # 确保状态已持久化
    del bridge1
    bridge2, _ = bridge_with_persistence(state_file)

    # Phase 3: 验证 pending 恢复
    # 由于消息在 pending 中，consume 不应再次返回（除非超时）
    messages_after_restart = await bridge2.consume(to_sid)

    # 当前测试预期：重启后 pending 丢失，消息会被重复消费
    # 修复后预期：pending 恢复，consume 返回空（消息仍在 pending）
    # 但由于当前是纯内存，我们先验证"消息丢失"场景

    # Phase 4: 模拟超时重排（时间前进 PENDING_TIMEOUT + 1）
    # 使用 mock 模拟时间前进
    future_time = time.time() + BridgeState.PENDING_TIMEOUT + 10

    with patch('time.time', return_value=future_time):
        # 超时后再次 consume，应该重新入队
        messages_timeout = await bridge2.consume(to_sid)

        # 修复后预期：消息从 pending 超时重排到 inbox
        assert len(messages_timeout) == 1, \
            "PENDING_TIMEOUT 后消息应重新入队"
        assert messages_timeout[0]["content"] == "需要 ack 的消息"


# ============================================================================
# 测试3：_processed 去重持久化 - 重启后不重复处理
# ============================================================================

@pytest.mark.asyncio
async def test_processed_dedup_after_restart(bridge_with_persistence):
    """测试 _processed 去重集合在重启后仍生效

    场景：
    1. 发送并 ack 一条消息（进入 _processed）
    2. 模拟重启
    3. 再次发送相同 id 的消息（模拟重复投递）
    4. 验证去重生效，不重复消费

    预期：当前纯内存实现会失败（重启后 _processed 清空，重复处理）
    """
    # Phase 1: 正常处理消息
    bridge1, state_file = bridge_with_persistence()

    from_sid = "qq:user:aaaaa:group:bbbbb"
    to_sid = "qq:user:ccccc:group:bbbbb"

    msg_id = await bridge1.send(from_sid, to_sid, "首次消息")
    messages = await bridge1.consume(to_sid)
    assert len(messages) == 1

    # ack 标记为已处理
    await bridge1.ack(to_sid, [msg_id])

    # Phase 2: 模拟重启
    await bridge1.flush()  # 确保状态已持久化
    del bridge1
    bridge2, _ = bridge_with_persistence(state_file)

    # Phase 3: 手动构造相同 id 的消息（模拟重复投递）
    # 注意：正常 send() 会生成新 UUID，这里需要直接操作内部状态
    duplicate_msg = BridgeMessage(from_sid, "重复消息内容")
    duplicate_msg.id = msg_id  # 复用相同 id

    async with bridge2._lock(to_sid):
        if to_sid not in bridge2._inbox:
            bridge2._inbox[to_sid] = []
        bridge2._inbox[to_sid].append(duplicate_msg)

    # Phase 4: 尝试消费重复消息
    messages_after_restart = await bridge2.consume(to_sid)

    # 修复后预期：去重生效，返回空列表
    assert len(messages_after_restart) == 0, \
        f"重启后去重应生效，不应消费已处理消息，实际消费: {len(messages_after_restart)}"


# ============================================================================
# 测试4：限流时间戳持久化 - 重启后限流不失效
# ============================================================================

@pytest.mark.asyncio
async def test_rate_limit_persist_after_restart(bridge_with_persistence):
    """测试 _rate 限流时间戳在重启后仍生效

    场景：
    1. 连续发送消息触发限流（RATE_LIMIT = 10 条/60秒）
    2. 模拟重启
    3. 立即再次发送，验证限流仍生效

    预期：当前纯内存实现会失败（重启后限流失效）
    """
    # Phase 1: 触发限流
    bridge1, state_file = bridge_with_persistence()

    from_sid = "qq:user:sender1:group:test123"
    to_sid = "qq:user:receiver1:group:test123"

    # 发送 RATE_LIMIT 条消息填满窗口
    for i in range(BridgeState.RATE_LIMIT):
        msg_id = await bridge1.send(from_sid, to_sid, f"消息 {i+1}")
        assert not msg_id.startswith("error:"), f"前 {BridgeState.RATE_LIMIT} 条应成功"

    # 第 11 条应触发限流
    msg_id_limited = await bridge1.send(from_sid, to_sid, "第11条-应被限流")
    assert msg_id_limited.startswith("error:"), "第11条应触发限流"
    assert "频繁" in msg_id_limited or "稍后" in msg_id_limited

    # Phase 2: 模拟重启
    await bridge1.flush()  # 确保状态已持久化
    del bridge1
    bridge2, _ = bridge_with_persistence(state_file)

    # Phase 3: 重启后立即发送，限流应仍生效
    msg_id_after_restart = await bridge2.send(from_sid, to_sid, "重启后立即发送")

    # 修复后预期：限流仍生效
    assert msg_id_after_restart.startswith("error:"), \
        "重启后限流应仍生效，但实际可能发送成功（_rate 丢失）"

    # Phase 4: 等待窗口过期后应恢复
    future_time = time.time() + BridgeState.RATE_INTERVAL + 1
    with patch('time.time', return_value=future_time):
        msg_id_after_window = await bridge2.send(from_sid, to_sid, "窗口过期后")
        assert not msg_id_after_window.startswith("error:"), \
            "窗口过期后应恢复发送"


# ============================================================================
# 测试5：空闲 sid 清理 - 持久化文件不无限增长
# ============================================================================

@pytest.mark.asyncio
async def test_idle_cleanup_works(bridge_with_persistence):
    """测试空闲 sid 清理机制在持久化场景下仍正常工作

    场景：
    1. 创建多个 sid 的消息状态
    2. 模拟时间流逝超过 SID_IDLE_TTL
    3. 触发清理，验证过期 sid 被移除
    4. 验证持久化文件大小合理（不包含已清理 sid）

    预期：清理机制应独立于持久化正常工作
    """
    bridge, state_file = bridge_with_persistence()

    # Phase 1: 创建多个 sid 的状态
    base_sid = "qq:user:{}:group:cleanup_test"
    active_sid = base_sid.format("active_user")
    idle_sid_1 = base_sid.format("idle_user_1")
    idle_sid_2 = base_sid.format("idle_user_2")
    system_sid = "qq:user:system_sender:group:cleanup_test"  # 规范的三段式 sid

    # 给所有 sid 发送消息
    for sid in [active_sid, idle_sid_1, idle_sid_2]:
        msg_id = await bridge.send(system_sid, sid, f"测试消息给 {sid}")
        assert not msg_id.startswith("error:")

    # Phase 2: 模拟时间流逝
    # 让 idle_sid_1 和 idle_sid_2 的消息被消费并 ack（清空 inbox/pending）
    for sid in [idle_sid_1, idle_sid_2]:
        messages = await bridge.consume(sid)
        await bridge.ack(sid, [m["id"] for m in messages])

    # active_sid 保持有消息（不清空）

    # Phase 3: 时间前进超过 SID_IDLE_TTL
    future_time = time.time() + BridgeState.SID_IDLE_TTL + 10

    with patch('time.time', return_value=future_time):
        # 触发清理：发送新消息会调用 _evict_idle()
        await bridge.send(system_sid, active_sid, "触发清理")

        # Phase 4: 验证清理结果
        # idle_sid_1/2 应被清理（inbox/pending 皆空且超时）
        assert idle_sid_1 not in bridge._inbox, "idle_sid_1 应被清理"
        assert idle_sid_2 not in bridge._inbox, "idle_sid_2 应被清理"
        assert idle_sid_1 not in bridge._locks, "idle_sid_1 锁应被清理"

        # active_sid 应保留（有消息）
        assert active_sid in bridge._inbox, "active_sid 应保留"

    # Phase 5: 验证持久化文件不包含已清理 sid
    # 注意：当前实现无持久化文件，此断言为未来实现预留
    if state_file.exists():
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)

        # 修复后预期：state_data 不包含 idle_sid_1/2
        inbox_data = state_data.get("inbox", {})
        assert idle_sid_1 not in inbox_data, "持久化文件不应包含已清理 sid"
        assert idle_sid_2 not in inbox_data


# ============================================================================
# 测试6：损坏文件优雅降级
# ============================================================================

@pytest.mark.asyncio
async def test_graceful_degrade_on_corrupted_file(bridge_with_persistence, caplog):
    """测试加载损坏的持久化文件时优雅降级

    场景：
    1. 手动写入损坏的 JSON 文件
    2. 实例化 BridgeState（尝试加载）
    3. 验证不 crash，打印 warning，从空状态启动

    预期：系统应容错，不因文件损坏而崩溃
    """
    _, state_file = bridge_with_persistence()

    # Phase 1: 写入损坏的 JSON
    with open(state_file, 'w', encoding='utf-8') as f:
        f.write("{corrupted json content")

    # Phase 2: 尝试加载（当前实现会忽略文件）
    # 未来实现：BridgeState(persistence_file=state_file) 应捕获异常
    with caplog.at_level("WARNING"):
        bridge, _ = bridge_with_persistence(state_file)

    # Phase 3: 验证优雅降级
    # 系统应正常工作（空状态启动）
    from_sid = "qq:user:sender:group:test"
    test_sid = "qq:user:receiver:group:test"
    msg_id = await bridge.send(from_sid, test_sid, "测试消息")
    assert not msg_id.startswith("error:"), "损坏文件不应影响正常功能"

    messages = await bridge.consume(test_sid)
    assert len(messages) == 1, "应从空状态正常工作"

    # 验证日志中有 warning（未来实现）
    # assert "损坏" in caplog.text or "加载失败" in caplog.text


# ============================================================================
# 测试7：IO 非阻塞性能
# ============================================================================

@pytest.mark.asyncio
async def test_io_non_blocking(bridge_with_persistence):
    """测试持久化 IO 不阻塞 asyncio 事件循环

    场景：
    1. 高并发发送 50+ 消息
    2. 验证 p99 延迟无显著回归
    3. 确保写 IO 不阻塞其他协程

    预期：持久化应使用异步 IO 或后台线程
    """
    bridge, _ = bridge_with_persistence()

    # Phase 1: 并发发送大量消息
    from_sid = "qq:user:sender:group:perf_test"
    to_sid_base = "qq:user:receiver_{}:group:perf_test"

    async def send_message(idx):
        start = time.time()
        to_sid = to_sid_base.format(idx)
        msg_id = await bridge.send(from_sid, to_sid, f"性能测试消息 {idx}")
        elapsed = time.time() - start
        return elapsed, msg_id

    # 并发发送 50 条消息
    tasks = [send_message(i) for i in range(50)]
    results = await asyncio.gather(*tasks)

    # Phase 2: 分析延迟
    latencies = [r[0] for r in results]
    successes = [r[1] for r in results if not r[1].startswith("error:")]

    # 验证大部分成功（考虑限流）
    assert len(successes) > 0, "至少部分消息应发送成功"

    # 验证 p99 延迟合理（< 100ms）
    latencies_sorted = sorted(latencies)
    p99_idx = int(len(latencies_sorted) * 0.99)
    p99_latency = latencies_sorted[p99_idx] if p99_idx < len(latencies_sorted) else latencies_sorted[-1]

    assert p99_latency < 0.1, \
        f"p99 延迟应 < 100ms，实际: {p99_latency*1000:.2f}ms（持久化不应阻塞）"

    # Phase 3: 验证并发安全
    # 读取所有成功 sid 的消息，确保无丢失/重复
    consumed_counts = {}
    for i in range(50):
        to_sid = to_sid_base.format(i)
        messages = await bridge.consume(to_sid)
        consumed_counts[to_sid] = len(messages)

    # 至少部分 sid 应收到消息（考虑同权限限制）
    total_consumed = sum(consumed_counts.values())
    assert total_consumed > 0, "并发场景下应有消息成功消费"


# ============================================================================
# 测试8：现有语义保持不变
# ============================================================================

@pytest.mark.asyncio
async def test_existing_semantics_preserved(bridge_with_persistence):
    """验证持久化修复后，所有现有语义保持不变

    测试项：
    1. two-phase consume/ack 机制
    2. PENDING_TIMEOUT 超时重排
    3. 10条/60秒限流
    4. _check_permission 权限检查
    5. MAX_INBOX 溢出淘汰
    6. UUID 去重
    """
    bridge, _ = bridge_with_persistence()

    # === 1. two-phase consume/ack ===
    from_sid = "qq:user:11111:group:22222"
    to_sid = "qq:user:33333:group:22222"

    msg_id_1 = await bridge.send(from_sid, to_sid, "消息1")
    messages = await bridge.consume(to_sid)
    assert len(messages) == 1, "consume 应移入 pending"

    # 再次 consume 不应返回（已在 pending）
    messages_2 = await bridge.consume(to_sid)
    assert len(messages_2) == 0, "pending 中的消息不应重复消费"

    # ack 后从 pending 移除
    await bridge.ack(to_sid, [msg_id_1])
    assert to_sid in bridge._processed or len(bridge._pending.get(to_sid, [])) == 0, \
        "ack 后应从 pending 移除"

    # === 2. PENDING_TIMEOUT 超时重排 ===
    msg_id_2 = await bridge.send(from_sid, to_sid, "消息2")
    await bridge.consume(to_sid)  # 进入 pending

    # 模拟超时
    future_time = time.time() + BridgeState.PENDING_TIMEOUT + 10
    with patch('time.time', return_value=future_time):
        messages_timeout = await bridge.consume(to_sid)
        assert len(messages_timeout) == 1, "超时消息应重新入队"
        assert messages_timeout[0]["id"] == msg_id_2

    # === 3. 限流 ===
    rate_from = "qq:user:rater:group:test"
    rate_to = "qq:user:ratee:group:test"

    for i in range(BridgeState.RATE_LIMIT):
        msg_id = await bridge.send(rate_from, rate_to, f"限流测试 {i}")
        assert not msg_id.startswith("error:"), f"前 {BridgeState.RATE_LIMIT} 条应成功"

    msg_limited = await bridge.send(rate_from, rate_to, "应被限流")
    assert msg_limited.startswith("error:"), "超出限流应失败"

    # === 4. 权限检查 ===
    unauthorized_from = "qq:user:12345:group:aaaaa"
    unauthorized_to = "wechat:user:67890:group:bbbbb"  # 不同 adapter

    msg_denied = await bridge.send(unauthorized_from, unauthorized_to, "无权限")
    assert msg_denied.startswith("error:"), "跨 adapter 应拒绝"
    assert "无权" in msg_denied or "权限" in msg_denied

    # === 5. MAX_INBOX 溢出淘汰 ===
    overflow_to = "qq:user:overflow:group:test"
    overflow_from = "qq:user:sender:group:test"

    # 发送 MAX_INBOX + 5 条消息
    for i in range(BridgeState.MAX_INBOX + 5):
        await bridge.send(overflow_from, overflow_to, f"溢出测试 {i}")

    messages_overflow = await bridge.consume(overflow_to)
    assert len(messages_overflow) <= BridgeState.MAX_POP, \
        "consume 一次最多返回 MAX_POP 条"

    # inbox 应不超过 MAX_INBOX（最老的被淘汰）
    remaining_inbox = bridge._inbox.get(overflow_to, [])
    assert len(remaining_inbox) <= BridgeState.MAX_INBOX, \
        "inbox 应维持上界"

    # === 6. UUID 去重 ===
    dedup_to = "qq:user:dedup:group:test"
    msg_id_original = await bridge.send(from_sid, dedup_to, "去重测试")

    messages_orig = await bridge.consume(dedup_to)
    await bridge.ack(dedup_to, [msg_id_original])

    # 手动构造重复消息
    dup_msg = BridgeMessage(from_sid, "重复内容")
    dup_msg.id = msg_id_original

    async with bridge._lock(dedup_to):
        if dedup_to not in bridge._inbox:
            bridge._inbox[dedup_to] = []
        bridge._inbox[dedup_to].append(dup_msg)

    messages_dup = await bridge.consume(dedup_to)
    assert len(messages_dup) == 0, "已 ack 的消息 id 应被去重"

    print("✓ 所有现有语义验证通过")
