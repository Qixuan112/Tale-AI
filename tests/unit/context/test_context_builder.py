"""Unit tests for ContextBuilder

测试完整的上下文构建流程：
- 组件集成
- 纯图消息问题#8修复验证
- 各种消息类型
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from core.chat.context_builder.context_builder import ContextBuilder
from core.chat.context_builder.metadata_builder import MetadataBuilder
from core.chat.context_builder.media_recognizer import MediaRecognizer
from core.chat.context_builder.history_provider import HistoryProvider
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType, EventType


@pytest.fixture
def metadata_builder():
    """创建 MetadataBuilder"""
    return MetadataBuilder()


@pytest.fixture
def media_recognizer():
    """创建 mock MediaRecognizer"""
    recognizer = Mock(spec=MediaRecognizer)
    recognizer.recognize_images = AsyncMock(return_value=None)
    return recognizer


@pytest.fixture
def history_provider():
    """创建 mock HistoryProvider"""
    provider = Mock(spec=HistoryProvider)
    provider.get_history_context = AsyncMock(return_value="")
    return provider


@pytest.fixture
def context_builder(metadata_builder, media_recognizer, history_provider):
    """创建 ContextBuilder"""
    return ContextBuilder(
        metadata_builder=metadata_builder,
        media_recognizer=media_recognizer,
        history_provider=history_provider
    )


@pytest.fixture
def basic_processed():
    """创建基础 ProcessedMessage"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.MESSAGE,
        sender_id="12345",
        sender_name="TestUser",
        text="Hello world",
        message_id="msg_001",
        group_id=None,
        group_name=None,
        at_targets=[],
        reply_to=None,
        reply_text=None,
        images=[],
        voices=[],
        faces=[],
        stickers=[],
        videos=[],
        files=[],
        reason="test"
    )


@pytest.mark.asyncio
async def test_build_input_simple_message(context_builder, basic_processed):
    """测试简单文本消息"""
    result = await context_builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    assert "[当前时间]" in result
    assert "[消息元数据]" in result
    assert "[环境信息]" in result
    assert "## 当前消息" in result
    assert "Hello world" in result


@pytest.mark.asyncio
async def test_build_input_with_image_recognition(context_builder, basic_processed, media_recognizer):
    """测试带图片识别的消息"""
    basic_processed.images = ["http://example.com/image.jpg"]
    media_recognizer.recognize_images.return_value = "一只可爱的猫"

    result = await context_builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    assert "[图片识别结果]" in result
    assert "一只可爱的猫" in result
    media_recognizer.recognize_images.assert_called_once()


@pytest.mark.asyncio
async def test_build_input_with_history(context_builder, basic_processed, history_provider):
    """测试带历史上下文的消息"""
    history_provider.get_history_context.return_value = "---\n[User1] Previous message\n---"

    result = await context_builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    assert "[User1] Previous message" in result
    history_provider.get_history_context.assert_called_once()


@pytest.mark.asyncio
async def test_build_input_issue_8_pure_image_with_history(
    context_builder, basic_processed, history_provider, media_recognizer
):
    """测试问题#8修复：纯图消息也应该加载历史上下文"""
    # 纯图消息：无文本，只有图片
    basic_processed.text = ""
    basic_processed.images = ["http://example.com/cat.jpg"]

    media_recognizer.recognize_images.return_value = "一只猫"
    history_provider.get_history_context.return_value = "---\n[User1] 看看我的猫\n---"

    result = await context_builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    # 验证历史上下文被加载
    history_provider.get_history_context.assert_called_once()
    assert "[User1] 看看我的猫" in result
    assert "一只猫" in result


@pytest.mark.asyncio
async def test_build_input_no_media_recognizer(metadata_builder, history_provider, basic_processed):
    """测试无图片识别器时跳过识别"""
    builder = ContextBuilder(
        metadata_builder=metadata_builder,
        media_recognizer=None,
        history_provider=history_provider
    )

    basic_processed.images = ["http://example.com/image.jpg"]

    result = await builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    assert "[图片识别结果]" not in result


@pytest.mark.asyncio
async def test_build_input_no_history_provider(metadata_builder, media_recognizer, basic_processed):
    """测试无历史提供器时跳过历史加载"""
    builder = ContextBuilder(
        metadata_builder=metadata_builder,
        media_recognizer=media_recognizer,
        history_provider=None
    )

    result = await builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    # 应该只有元数据和当前消息
    assert "[当前时间]" in result
    assert "## 当前消息" in result


@pytest.mark.asyncio
async def test_build_input_section_order(context_builder, basic_processed, media_recognizer, history_provider):
    """测试段落顺序：元数据 → 图片识别 → 历史 → 当前消息"""
    basic_processed.images = ["http://example.com/image.jpg"]
    media_recognizer.recognize_images.return_value = "识别结果"
    history_provider.get_history_context.return_value = "---\n历史消息\n---"

    result = await context_builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    # 检查顺序
    metadata_pos = result.find("[当前时间]")
    image_pos = result.find("[图片识别结果]")
    history_pos = result.find("历史消息")
    current_pos = result.find("## 当前消息")

    assert metadata_pos < image_pos < history_pos < current_pos


@pytest.mark.asyncio
async def test_build_input_persistence_mode(context_builder, basic_processed, history_provider):
    """测试持久化模式传递参数"""
    await context_builder.build_input(
        basic_processed,
        platform_name="qq",
        persistence_enabled=True,
        session_enabled=True
    )

    # 验证参数正确传递给 HistoryProvider
    call_kwargs = history_provider.get_history_context.call_args[1]
    assert call_kwargs['persistence_enabled'] is True
    assert call_kwargs['session_enabled'] is True


@pytest.mark.asyncio
async def test_build_input_window_size(context_builder, basic_processed, history_provider):
    """测试窗口大小参数传递"""
    await context_builder.build_input(
        basic_processed,
        platform_name="qq",
        window=10
    )

    call_kwargs = history_provider.get_history_context.call_args[1]
    assert call_kwargs['window'] == 10


@pytest.mark.asyncio
async def test_build_input_image_recognition_failed(context_builder, basic_processed, media_recognizer):
    """测试图片识别失败时不影响其他部分"""
    basic_processed.images = ["http://example.com/image.jpg"]
    media_recognizer.recognize_images.return_value = None  # 识别失败

    result = await context_builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    assert "[图片识别结果]" not in result
    assert "## 当前消息" in result  # 其他部分正常


@pytest.mark.asyncio
async def test_build_input_with_at_and_reply(context_builder, basic_processed):
    """测试带 @ 和回复的消息"""
    basic_processed.at_targets = ["user1"]
    basic_processed.reply_to = "msg_000"
    basic_processed.reply_text = "Previous"

    result = await context_builder.build_input(
        basic_processed,
        platform_name="qq"
    )

    assert "[At user1]" in result
    assert "[回复: Previous]" in result
    assert "Hello world" in result
