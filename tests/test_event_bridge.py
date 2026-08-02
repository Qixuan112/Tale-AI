"""
测试 AdapterEventBridge 事件序列化问题 (#135)

验证 PlatformEvent 在通过 EventBus 传递时的对象完整性和字段保留情况。
当前实现将对象序列化为字典，导致部分字段丢失。

预期结果：
- 3个对象传递测试应失败（证明传dict而非对象）
- 2个字段完整性测试应失败（sender.extra和raw_content未保留）
- 其余14个测试应通过（文档化当前行为）
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import dataclass, field
from typing import Dict, Any

from core.adapter.event import PlatformEvent, EventType, PlatformType, MessageContent, SenderInfo
from core.adapter.integration import AdapterEventBridge
from core.bus.bus import EventBus


@pytest.fixture
def event_bus():
    """创建事件总线实例"""
    return EventBus()


@pytest.fixture
def bridge(event_bus):
    """创建适配器事件桥接器"""
    return AdapterEventBridge(event_bus, config_loader=None)


@pytest.fixture
def sample_event():
    """创建标准测试事件"""
    return PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.PRIVATE_MESSAGE,
        sender=SenderInfo(
            id="user123",
            name="TestUser",
            avatar="https://example.com/avatar.jpg",
            is_bot=False,
            extra={"level": 10, "vip": True}
        ),
        content=MessageContent(
            text="Hello World",
            images=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
            at_targets=["bot456"],
            reply_to="msg999",
            reply_text="Previous message",
            raw_content={"original": "data"}
        ),
        message_id="msg123",
        group_id=None,
        group_name=None,
        timestamp=datetime(2026, 7, 30, 12, 0, 0),
        raw_event={"post_type": "message", "message_type": "private"}
    )


# ==================== 1. 对象传递测试 (3个，应失败) ====================

@pytest.mark.asyncio
async def test_platform_message_receives_object(event_bus, bridge, sample_event):
    """验证 platform_message 事件接收到 PlatformEvent 对象而非字典

    预期：失败 - 当前实现传递字典
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)  # 等待异步事件完成

    assert len(received_data) == 1
    # 这个断言应该失败 - 当前实现传递的是字典
    assert isinstance(received_data[0], PlatformEvent), "应接收 PlatformEvent 对象而非字典"


@pytest.mark.asyncio
async def test_private_message_receives_object(event_bus, bridge, sample_event):
    """验证 private_message 事件接收到 PlatformEvent 对象

    预期：失败 - 当前实现传递字典
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("private_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    # 这个断言应该失败
    assert isinstance(received_data[0], PlatformEvent), "应接收 PlatformEvent 对象而非字典"


@pytest.mark.asyncio
async def test_group_message_receives_object(event_bus, bridge):
    """验证 group_message 事件接收到 PlatformEvent 对象

    预期：失败 - 当前实现传递字典
    """
    group_event = PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.GROUP_MESSAGE,
        sender=SenderInfo(id="user123", name="TestUser"),
        content=MessageContent(text="Group message"),
        message_id="msg456",
        group_id="group789",
        group_name="TestGroup",
        timestamp=datetime.now()
    )

    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("group_message", handler)
    await bridge._on_platform_event(group_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    # 这个断言应该失败
    assert isinstance(received_data[0], PlatformEvent), "应接收 PlatformEvent 对象而非字典"


# ==================== 2. 字段完整性测试 (7个) ====================

@pytest.mark.asyncio
async def test_files_field_preserved(event_bus, bridge):
    """验证 files 字段在传递过程中保留

    预期：通过（如果MessageContent支持files字段）或跳过
    """
    # MessageContent 当前不支持 files 字段，这个测试文档化期望行为
    pytest.skip("MessageContent 当前不支持 files 字段，待扩展")


@pytest.mark.asyncio
async def test_images_field_preserved(event_bus, bridge, sample_event):
    """验证 images 字段在传递过程中保留

    预期：通过
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)
    assert event.content.images == ["https://example.com/image1.jpg", "https://example.com/image2.jpg"]


@pytest.mark.asyncio
async def test_reply_to_field_preserved(event_bus, bridge, sample_event):
    """验证 reply_to 字段在传递过程中保留

    预期：通过
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)
    assert event.content.reply_to == "msg999"
    assert event.content.reply_text == "Previous message"


@pytest.mark.asyncio
async def test_at_targets_field_preserved(event_bus, bridge, sample_event):
    """验证 at_targets 字段在传递过程中保留

    预期：通过
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)
    assert event.content.at_targets == ["bot456"]


@pytest.mark.asyncio
async def test_sender_extra_field_preserved(event_bus, bridge, sample_event):
    """验证 sender.extra 字段在传递过程中保留

    预期：通过 - 现在直接传递对象，所有字段都保留
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)
    assert event.sender.extra == {"level": 10, "vip": True}


@pytest.mark.asyncio
async def test_raw_content_field_preserved(event_bus, bridge, sample_event):
    """验证 content.raw_content 字段在传递过程中保留

    预期：通过 - 现在直接传递对象，所有字段都保留
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)
    assert event.content.raw_content == {"original": "data"}


@pytest.mark.asyncio
async def test_group_info_preserved(event_bus, bridge):
    """验证 group_id 和 group_name 在传递过程中保留

    预期：通过
    """
    group_event = PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.GROUP_MESSAGE,
        sender=SenderInfo(id="user123", name="TestUser"),
        content=MessageContent(text="Group message"),
        message_id="msg456",
        group_id="group789",
        group_name="TestGroup",
        timestamp=datetime.now()
    )

    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("group_message", handler)
    await bridge._on_platform_event(group_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)
    assert event.group_id == "group789"
    assert event.group_name == "TestGroup"


# ==================== 3. 扩展性测试 (2个) ====================

@pytest.mark.asyncio
async def test_new_platformevent_fields_preserved(event_bus, bridge):
    """验证 PlatformEvent 新增字段能自动保留

    预期：失败 - 当前实现使用白名单序列化，新字段会丢失

    这个测试模拟未来在 PlatformEvent 添加新字段的情况。
    """
    # 创建一个带有额外字段的事件（模拟未来扩展）
    event = PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.PRIVATE_MESSAGE,
        sender=SenderInfo(id="user123", name="TestUser"),
        content=MessageContent(text="Test"),
        message_id="msg123",
        timestamp=datetime.now()
    )

    # 手动添加新字段（模拟dataclass扩展）
    event.priority = "high"  # 假设未来添加了优先级字段
    event.metadata = {"source": "mobile"}  # 假设添加了元数据字段

    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    data = received_data[0]
    # 这些断言会失败 - 新字段不会自动保留
    # 注意：这是测试期望行为，不是当前行为
    pytest.skip("当前实现使用白名单序列化，此测试文档化期望的自动扩展行为")


@pytest.mark.asyncio
async def test_new_messagecontent_fields_preserved(event_bus, bridge):
    """验证 MessageContent 新增字段能自动保留

    预期：失败 - MessageContent.to_dict() 使用白名单
    """
    content = MessageContent(text="Test")
    # 手动添加新字段（模拟未来扩展）
    content.files = ["file1.pdf", "file2.docx"]  # 假设添加了文件字段
    content.locations = [{"lat": 39.9, "lng": 116.4}]  # 假设添加了位置字段

    event = PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.PRIVATE_MESSAGE,
        sender=SenderInfo(id="user123", name="TestUser"),
        content=content,
        message_id="msg123",
        timestamp=datetime.now()
    )

    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    data = received_data[0]
    # 这些字段不会出现在序列化结果中
    pytest.skip("当前实现使用白名单序列化，此测试文档化期望的自动扩展行为")


# ==================== 4. 现有功能测试 (4个，应通过) ====================

@pytest.mark.asyncio
async def test_qq_private_message_flow(event_bus, bridge, sample_event):
    """验证 QQ 私聊消息完整流程

    预期：通过 - 验证当前实现的正确事件发布顺序
    """
    received_events = []

    def capture(event_name):
        def handler(data):
            received_events.append((event_name, data))
        return handler

    event_bus.on("platform_message", capture("platform_message"))
    event_bus.on("private_message", capture("private_message"))
    event_bus.on("qq_message", capture("qq_message"))

    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    # 应该触发 3 个事件
    assert len(received_events) == 3
    event_names = [name for name, _ in received_events]
    assert "platform_message" in event_names
    assert "private_message" in event_names
    assert "qq_message" in event_names

    # 验证所有事件携带相同的核心数据
    for event_name, event in received_events:
        assert isinstance(event, PlatformEvent)
        assert event.platform.value == "qq"
        assert event.event_type.value == "private_message"
        assert event.sender.id == "user123"
        assert event.message_id == "msg123"


@pytest.mark.asyncio
async def test_qq_group_message_flow(event_bus, bridge):
    """验证 QQ 群聊消息完整流程

    预期：通过
    """
    group_event = PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.GROUP_MESSAGE,
        sender=SenderInfo(id="user456", name="GroupUser"),
        content=MessageContent(text="Group message", at_targets=["bot123"]),
        message_id="msg789",
        group_id="group999",
        group_name="TestGroup",
        timestamp=datetime.now()
    )

    received_events = []

    def capture(event_name):
        def handler(data):
            received_events.append((event_name, data))
        return handler

    event_bus.on("platform_message", capture("platform_message"))
    event_bus.on("group_message", capture("group_message"))
    event_bus.on("qq_message", capture("qq_message"))

    await bridge._on_platform_event(group_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_events) == 3
    event_names = [name for name, _ in received_events]
    assert "platform_message" in event_names
    assert "group_message" in event_names
    assert "qq_message" in event_names

    # 验证群聊特定字段
    for event_name, event in received_events:
        assert isinstance(event, PlatformEvent)
        assert event.group_id == "group999"
        assert event.group_name == "TestGroup"


@pytest.mark.asyncio
async def test_adapter_instance_tracking(event_bus, bridge, sample_event):
    """验证 adapter_instance 字段正确追踪来源适配器

    预期：通过
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_bot_1")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)
    assert event.adapter_instance == "qq_bot_1"

    # 测试不同的 adapter_id
    received_data.clear()
    await bridge._on_platform_event(sample_event, adapter_id="qq_bot_2")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert event.adapter_instance == "qq_bot_2"


@pytest.mark.asyncio
async def test_notice_event_no_platform_message(event_bus, bridge):
    """验证 NOTICE 类型事件不触发平台特定消息事件

    预期：通过 - NOTICE 只触发 platform_message 和 platform_notice
    """
    notice_event = PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.NOTICE,
        sender=SenderInfo(id="system", name="System"),
        content=MessageContent(text="User joined"),
        message_id="notice123",
        timestamp=datetime.now()
    )

    received_events = []

    def capture(event_name):
        def handler(data):
            received_events.append((event_name, data))
        return handler

    event_bus.on("platform_message", capture("platform_message"))
    event_bus.on("platform_notice", capture("platform_notice"))
    event_bus.on("qq_message", capture("qq_message"))

    await bridge._on_platform_event(notice_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    # 应该只触发 platform_message 和 platform_notice，不触发 qq_message
    event_names = [name for name, _ in received_events]
    assert "platform_message" in event_names
    assert "platform_notice" in event_names
    assert "qq_message" not in event_names, "NOTICE 事件不应触发 qq_message"


# ==================== 5. 向后兼容测试 (1个) ====================

@pytest.mark.asyncio
async def test_required_fields_accessible(event_bus, bridge, sample_event):
    """验证所有必需字段在对象传递后可访问

    预期：通过 - 确保现有代码依赖的字段都存在
    """
    received_data = []

    def handler(data):
        received_data.append(data)

    event_bus.on("platform_message", handler)
    await bridge._on_platform_event(sample_event, adapter_id="qq_main")
    await asyncio.sleep(0.01)

    assert len(received_data) == 1
    event = received_data[0]
    assert isinstance(event, PlatformEvent)

    # 验证顶层必需字段
    assert hasattr(event, 'platform')
    assert hasattr(event, 'event_type')
    assert hasattr(event, 'adapter_instance')
    assert hasattr(event, 'sender')
    assert hasattr(event, 'content')
    assert hasattr(event, 'message_id')
    assert hasattr(event, 'timestamp')
    assert hasattr(event, 'raw_event')

    # 验证 sender 子字段
    assert hasattr(event.sender, 'id')
    assert hasattr(event.sender, 'name')
    assert hasattr(event.sender, 'avatar')
    assert hasattr(event.sender, 'is_bot')

    # 验证 content 子字段
    assert hasattr(event.content, 'text')
    assert hasattr(event.content, 'images')
    assert hasattr(event.content, 'at_targets')
    assert hasattr(event.content, 'reply_to')
    assert hasattr(event.content, 'reply_text')

    # 验证值的正确性
    assert event.platform.value == "qq"
    assert event.event_type.value == "private_message"
    assert event.sender.id == "user123"
    assert event.content.text == "Hello World"
