"""
集成测试：验证 #134 内存泄漏修复（BoundedCache 边界行为）

#134 已将 _chat_context_buffer / _name_to_id 从无界 dict 替换为
BoundedCache（maxsize=200, ttl 7h/24h），消息缓冲区截断为每键 100 条。

这些测试验证修复后的边界行为：缓存键数不超过 maxsize（LRU 淘汰），
单群消息缓冲不超过 100 条，昵称映射按群分组、改名时新旧昵称并存。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.main import TaleCore
from core.adapter.event import (
    PlatformEvent,
    PlatformType,
    EventType,
    MessageContent,
    SenderInfo,
)
from core.adapter.message_processor import ProcessedMessage, ResponseDecision
from datetime import datetime


@pytest.fixture
def mock_config():
    """Mock 配置加载器"""
    # 用 importlib 取真实模块对象，绕开 core/__init__.py 的 from .main import main
    # 对 core.main 属性的遮蔽（遮蔽后 patch("core.main.config_loader") 会解析到
    # 函数 main 而非模块，CI 收集顺序下抛 AttributeError）
    import importlib
    _main_mod = importlib.import_module("core.main")
    with patch.object(_main_mod, "config_loader") as mock_loader:
        # Mock bot config
        mock_loader.bot.bot.persistence_enabled = False
        mock_loader.bot.bot.typing_speed = 200.0
        mock_loader.bot.bot.typing_min_delay = 2.0
        mock_loader.bot.bot.typing_inter_delay = 2.0
        mock_loader.bot.bot.max_agent_steps = 5
        mock_loader.bot.bot.per_step_timeout = 30.0
        # initialize() 中 asyncio.Semaphore(max_concurrent_llm) 需要真实的 int，
        # 否则 MagicMock 自动生成的子 mock 无法与 0 比较（asyncio.locks.py:347）
        mock_loader.bot.bot.max_concurrent_llm = 3

        # Mock context config
        mock_loader.bot.context.chat_context_enabled = False
        mock_loader.bot.context.chat_context_window = 0

        # Mock wake config
        mock_loader.bot.wake.waking_keywords = []
        mock_loader.bot.wake.enable_keyword_wake = False
        mock_loader.bot.wake.enable_quote_wake = False

        # Mock adapters config
        mock_loader.adapters.qq.enabled = False

        yield mock_loader


@pytest.fixture
def core(mock_config):
    """创建 TaleCore 实例（不初始化 LLM）"""
    import importlib
    _main_mod = importlib.import_module("core.main")
    with patch.object(_main_mod, "ChatLLM"), \
         patch.object(_main_mod, "ToolLLM"), \
         patch.object(_main_mod, "get_planllm"), \
         patch.object(_main_mod, "get_vlm_llm"), \
         patch.object(_main_mod, "bus"):

        tale_core = TaleCore()
        tale_core.initialize()
        # Mock message processor
        tale_core.message_processor = Mock()
        tale_core.message_processor.process = Mock()

        yield tale_core


def create_processed_message(
    group_id=None,
    sender_id="user123",
    sender_name="TestUser",
    text="test message",
    images=None,
    decision=ResponseDecision.SILENT,
):
    """创建 ProcessedMessage 对象"""
    msg = Mock(spec=ProcessedMessage)
    msg.group_id = group_id
    msg.sender_id = sender_id
    msg.sender_name = sender_name
    msg.text = text
    msg.images = images or []
    # files 无默认值（default_factory），dataclass 处理后被从类属性移除，
    # 导致 spec mock 不包含该属性，直接访问会抛 AttributeError
    msg.files = []
    msg.decision = decision
    msg.reason = "test"
    msg.platform = PlatformType.QQ
    msg.message_id = "msg123"
    msg.is_group_message = group_id is not None
    return msg


# ============================================================================
# 测试组 1: context buffer 泄漏 (6 个)
# ============================================================================

def test_context_buffer_per_group_limit_100(core):
    """测试单群消息缓冲区上限 100 条"""
    group_id = "test_group_001"

    # 发送 150 条消息
    for i in range(150):
        msg = create_processed_message(
            group_id=group_id,
            sender_name=f"User{i % 10}",
            text=f"Message {i}",
        )
        core._store_to_context_buffer(msg)

    # 验证该群只保留最近 100 条
    assert group_id in core._chat_context_buffer
    assert len(core._chat_context_buffer[group_id]) == 100

    # 验证是最新的 100 条（50-149）
    first_msg = core._chat_context_buffer[group_id][0]
    assert "Message 50" in first_msg["text"]


def test_context_buffer_bounded_groups_500(core):
    """测试 500 个群时缓冲区不超过 BoundedCache 上限（LRU 淘汰最旧的群）"""
    # 模拟 500 个不同群聊各发送 10 条消息
    for group_idx in range(500):
        group_id = f"group_{group_idx:04d}"
        for msg_idx in range(10):
            msg = create_processed_message(
                group_id=group_id,
                sender_name=f"User{msg_idx}",
                text=f"Group {group_idx} Message {msg_idx}",
            )
            core._store_to_context_buffer(msg)

    # 验证有界：500 个群只保留最近 200 个（maxsize=200），最旧的被 LRU 淘汰
    assert len(core._chat_context_buffer) == 200
    assert "group_0000" not in core._chat_context_buffer  # 最早写入的群被淘汰
    assert "group_0499" in core._chat_context_buffer       # 最近写入的群保留

    # 验证保留的每个群有 10 条消息
    for group_idx in range(300, 500):
        group_id = f"group_{group_idx:04d}"
        assert group_id in core._chat_context_buffer
        assert len(core._chat_context_buffer[group_id]) == 10


def test_context_buffer_bounded_mixed_600_groups_and_dm(core):
    """测试 600 群 + 私聊混合场景下缓冲区保持有界"""
    # 600 个群聊各 5 条消息
    for group_idx in range(600):
        group_id = f"group_{group_idx:04d}"
        for msg_idx in range(5):
            msg = create_processed_message(
                group_id=group_id,
                sender_name=f"User{msg_idx}",
                text=f"Group message {msg_idx}",
            )
            core._store_to_context_buffer(msg)

    # 100 个私聊各 5 条消息
    for user_idx in range(100):
        sender_id = f"user_{user_idx:04d}"
        for msg_idx in range(5):
            msg = create_processed_message(
                group_id=None,
                sender_id=sender_id,
                sender_name=f"PrivateUser{user_idx}",
                text=f"DM message {msg_idx}",
            )
            core._store_to_context_buffer(msg)

    # 验证有界：700 键只保留最近 200 个（后写入的 100 个私聊 + 最后 100 个群）
    assert len(core._chat_context_buffer) == 200
    assert "group_0000" not in core._chat_context_buffer   # 最早写入的群被淘汰
    assert "group_0599" in core._chat_context_buffer       # 最近写入的群保留
    assert "user_0099" in core._chat_context_buffer        # 后写入的私聊全部保留
    assert "user_0000" in core._chat_context_buffer


def test_context_buffer_empty_messages_not_stored(core):
    """测试空消息不存储到缓冲区"""
    group_id = "test_group_empty"

    # 空文本无图片
    msg1 = create_processed_message(
        group_id=group_id,
        text="",
        images=[],
    )
    core._store_to_context_buffer(msg1)

    # 空文本但有图片（应存储）
    msg2 = create_processed_message(
        group_id=group_id,
        text="",
        images=["http://example.com/image.jpg"],
    )
    core._store_to_context_buffer(msg2)

    # 验证只有带图片的消息被存储
    assert group_id in core._chat_context_buffer
    assert len(core._chat_context_buffer[group_id]) == 1


def test_context_buffer_with_images_stored(core):
    """测试带图片消息正确存储"""
    group_id = "test_group_images"

    # 发送带图片的消息
    images = [
        "http://example.com/img1.jpg",
        "http://example.com/img2.png",
    ]
    msg = create_processed_message(
        group_id=group_id,
        text="Check these images",
        images=images,
    )
    core._store_to_context_buffer(msg)

    # 验证图片被存储
    assert group_id in core._chat_context_buffer
    stored = core._chat_context_buffer[group_id][0]
    assert "images" in stored
    assert len(stored["images"]) == 2
    assert stored["images"][0] == "http://example.com/img1.jpg"


def test_context_buffer_with_files_stored(core):
    """测试带文件消息存储（通过文本标记）"""
    group_id = "test_group_files"

    # 模拟文件消息（在实际实现中文件会作为文本描述）
    msg = create_processed_message(
        group_id=group_id,
        text="[文件: document.pdf]",
        images=[],
    )
    core._store_to_context_buffer(msg)

    # 验证文件消息被存储
    assert group_id in core._chat_context_buffer
    stored = core._chat_context_buffer[group_id][0]
    assert "[文件:" in stored["text"]


# ============================================================================
# 测试组 2: name_to_id 泄漏 (3 个)
# ============================================================================

def test_name_to_id_bounded_500_groups(core):
    """测试 500 群时 name_to_id 不超过 BoundedCache 上限（LRU 淘汰最旧的群）"""
    # 模拟 500 个群各有 10 个用户发言
    for group_idx in range(500):
        group_id = f"group_{group_idx:04d}"
        for user_idx in range(10):
            msg = create_processed_message(
                group_id=group_id,
                sender_id=f"qq_{user_idx:04d}",
                sender_name=f"用户{user_idx}",
                text="test",
                decision=ResponseDecision.RESPOND,
            )

            # 直接调用 name_to_id 更新逻辑（模拟 _handle_respond_message 中的代码）
            if msg.sender_name and msg.sender_id:
                group_key = msg.group_id or "_private"
                if group_key not in core._name_to_id:
                    core._name_to_id[group_key] = {}
                core._name_to_id[group_key][msg.sender_name] = msg.sender_id

    # 验证有界：500 个群只保留最近 200 个（maxsize=200），最旧的被 LRU 淘汰
    assert len(core._name_to_id) == 200
    assert "group_0000" not in core._name_to_id  # 最早写入的群被淘汰
    assert "group_0499" in core._name_to_id      # 最近写入的群保留

    # 验证保留的每个群有 10 个用户映射
    for group_idx in range(300, 500):
        group_id = f"group_{group_idx:04d}"
        assert group_id in core._name_to_id
        assert len(core._name_to_id[group_id]) == 10


def test_name_to_id_private_chats_under_private_key(core):
    """测试私聊昵称映射在 _private 键下"""
    # 模拟 50 个不同用户的私聊
    for user_idx in range(50):
        msg = create_processed_message(
            group_id=None,
            sender_id=f"user_{user_idx:04d}",
            sender_name=f"私聊用户{user_idx}",
            text="private message",
        )

        # 模拟 _handle_respond_message 中的映射逻辑
        if msg.sender_name and msg.sender_id:
            group_key = msg.group_id or "_private"
            if group_key not in core._name_to_id:
                core._name_to_id[group_key] = {}
            core._name_to_id[group_key][msg.sender_name] = msg.sender_id

    # 验证所有私聊用户在 _private 键下
    assert "_private" in core._name_to_id
    assert len(core._name_to_id["_private"]) == 50


def test_name_to_id_user_rename_updates(core):
    """测试用户改名时映射更新"""
    group_id = "test_group_rename"
    user_id = "qq_12345"

    # 初始昵称
    msg1 = create_processed_message(
        group_id=group_id,
        sender_id=user_id,
        sender_name="旧昵称",
        text="first message",
    )
    if msg1.sender_name and msg1.sender_id:
        group_key = msg1.group_id or "_private"
        if group_key not in core._name_to_id:
            core._name_to_id[group_key] = {}
        core._name_to_id[group_key][msg1.sender_name] = msg1.sender_id

    # 用户改名后发言
    msg2 = create_processed_message(
        group_id=group_id,
        sender_id=user_id,
        sender_name="新昵称",
        text="second message",
    )
    if msg2.sender_name and msg2.sender_id:
        group_key = msg2.group_id or "_private"
        if group_key not in core._name_to_id:
            core._name_to_id[group_key] = {}
        core._name_to_id[group_key][msg2.sender_name] = msg2.sender_id

    # 验证新旧昵称都存在（证明累积，不清理旧映射）
    assert "旧昵称" in core._name_to_id[group_id]
    assert "新昵称" in core._name_to_id[group_id]
    assert len(core._name_to_id[group_id]) == 2


# ============================================================================
# 测试组 3: 内存泄漏模拟 (2 个)
# ============================================================================

def test_memory_leak_24h_real_load_simulation(core):
    """模拟 24 小时真实负载的内存累积

    假设：
    - 200 个活跃群
    - 每群平均 100 条消息/天
    - 每群平均 50 个活跃用户/天
    """
    num_groups = 200
    messages_per_group = 100
    users_per_group = 50

    for group_idx in range(num_groups):
        group_id = f"active_group_{group_idx:03d}"

        # 模拟消息流
        for msg_idx in range(messages_per_group):
            user_idx = msg_idx % users_per_group
            msg = create_processed_message(
                group_id=group_id,
                sender_id=f"user_{user_idx:04d}",
                sender_name=f"用户{user_idx}",
                text=f"Message {msg_idx} from user {user_idx}",
            )
            core._store_to_context_buffer(msg)

            # 更新 name_to_id（走 BoundedCache 写时复制路径，触发 LRU/TTL 刷新）
            if msg.sender_name and msg.sender_id:
                group_key = msg.group_id or "_private"
                name_map = core._name_to_id.get(group_key, {})
                name_map[msg.sender_name] = msg.sender_id
                core._name_to_id[group_key] = name_map

    # 验证内存有界：200 个活跃群全部在 200 上限内
    assert len(core._chat_context_buffer) == 200
    assert len(core._name_to_id) == 200

    # 验证每个群的缓冲区达到上限
    for group_idx in range(num_groups):
        group_id = f"active_group_{group_idx:03d}"
        assert len(core._chat_context_buffer[group_id]) == 100  # 上限
        assert len(core._name_to_id[group_id]) == 50  # 所有用户


def test_memory_leak_zombie_groups_accumulation(core):
    """测试僵尸群累积（加入后从未活跃的群）

    模拟场景：
    - 机器人加入 1000 个群
    - 每个群只收到 1 条入群欢迎消息
    - 之后再无活动
    """
    num_zombie_groups = 1000

    for group_idx in range(num_zombie_groups):
        group_id = f"zombie_group_{group_idx:04d}"

        # 每个群只有 1 条消息
        msg = create_processed_message(
            group_id=group_id,
            sender_id="bot_123",
            sender_name="机器人",
            text="欢迎加入本群",
        )
        core._store_to_context_buffer(msg)

        # 更新 name_to_id（走 BoundedCache 写时复制路径，触发 LRU/TTL 刷新）
        if msg.sender_name and msg.sender_id:
            group_key = msg.group_id or "_private"
            name_map = core._name_to_id.get(group_key, {})
            name_map[msg.sender_name] = msg.sender_id
            core._name_to_id[group_key] = name_map

    # 验证僵尸群不导致无界累积：1000 个僵尸群只保留最近 200 个（maxsize=200）
    assert len(core._chat_context_buffer) == 200
    assert len(core._name_to_id) == 200
    assert "zombie_group_0000" not in core._chat_context_buffer  # 最早加入的群被淘汰
    assert "zombie_group_0999" in core._chat_context_buffer      # 最近活跃的群保留

    # 验证保留下来的群占用最少的 1 条消息内存
    for group_idx in range(800, 1000):
        group_id = f"zombie_group_{group_idx:04d}"
        assert group_id in core._chat_context_buffer
        assert len(core._chat_context_buffer[group_id]) == 1


# ============================================================================
# 测试组 4: 内存增长测量 (1 个)
# ============================================================================

def test_memory_growth_bounded_scaling(core):
    """测量不同群数下的内存占用，验证有界而非线性增长

    测试 100/500/1000/2000 群的内存占用：键数量应保持在上限 200，
    而不是随群数线性增长（证明 #134 修复生效）。
    """
    measurements = {}
    group_counts = [100, 500, 1000, 2000]

    for num_groups in group_counts:
        # 清空现有数据
        core._chat_context_buffer.clear()
        core._name_to_id.clear()

        # 模拟群消息
        for group_idx in range(num_groups):
            group_id = f"group_{group_idx:05d}"

            # 每群 50 条消息，20 个用户
            for msg_idx in range(50):
                user_idx = msg_idx % 20
                msg = create_processed_message(
                    group_id=group_id,
                    sender_id=f"user_{user_idx:04d}",
                    sender_name=f"用户{user_idx}",
                    text=f"Message {msg_idx}",
                )
                core._store_to_context_buffer(msg)

                # 更新 name_to_id（走 BoundedCache 写时复制路径，触发 LRU/TTL 刷新）
                if msg.sender_name and msg.sender_id:
                    group_key = msg.group_id or "_private"
                    name_map = core._name_to_id.get(group_key, {})
                    name_map[msg.sender_name] = msg.sender_id
                    core._name_to_id[group_key] = name_map

        # 测量内存占用
        buffer_size = sys.getsizeof(core._chat_context_buffer)
        name_map_size = sys.getsizeof(core._name_to_id)

        measurements[num_groups] = {
            "buffer_keys": len(core._chat_context_buffer),
            "name_map_keys": len(core._name_to_id),
            "buffer_size_bytes": buffer_size,
            "name_map_size_bytes": name_map_size,
        }

    # 验证键数量有界：100 群内全部保留，超过 200 上限后不再增长
    assert measurements[100]["buffer_keys"] == 100
    assert measurements[500]["buffer_keys"] == 200
    assert measurements[1000]["buffer_keys"] == 200
    assert measurements[2000]["buffer_keys"] == 200

    # 验证 name_to_id 同步有界
    assert measurements[100]["name_map_keys"] == 100
    assert measurements[500]["name_map_keys"] == 200
    assert measurements[1000]["name_map_keys"] == 200
    assert measurements[2000]["name_map_keys"] == 200

    # 验证内存占用不随群数显著增长：sys.getsizeof 只测量容器自身，
    # 键数量封顶 + 每次 __setitem__ 写时复制（值被 dict 化/截断）即可
    # 证明有界；记录比值仅作诊断信息，不做断言（shallow 大小受 Python
    # 内部字典扩容对齐影响，比值不可靠）。
    buffer_size = measurements[2000]["buffer_size_bytes"]
    name_map_size = measurements[2000]["name_map_size_bytes"]
    print(
        f"Buffer shallow size @2000 groups: {buffer_size}B "
        f"(ratio vs 100 groups: {buffer_size / measurements[100]['buffer_size_bytes']:.2f})"
    )
    print(
        f"NameMap shallow size @2000 groups: {name_map_size}B "
        f"(ratio vs 100 groups: {name_map_size / measurements[100]['name_map_size_bytes']:.2f})"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
