"""Integration tests for context builder modules

测试各模块集成工作，验证端到端流程。
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from core.chat.context_builder import (
    ContextBuilder,
    MetadataBuilder,
    MediaRecognizer,
    HistoryProvider
)
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType, EventType
from core.utils.id_sanitizer import IDSanitizer


@pytest.fixture
def real_metadata_builder():
    """创建真实的 MetadataBuilder"""
    return MetadataBuilder(IDSanitizer())


@pytest.fixture
def mock_vlm():
    """创建 mock VLM"""
    vlm = Mock()
    vlm._ensure_provider = Mock(return_value=True)
    vlm.chat_with_image = Mock(return_value="图片内容：一只猫")
    return vlm


@pytest.fixture
def real_media_recognizer(mock_vlm):
    """创建真实的 MediaRecognizer（无线程池，同步模式）"""
    return MediaRecognizer(vlm=mock_vlm, timeout=3.0, executor=None)


@pytest.fixture
def real_history_provider():
    """创建真实的 HistoryProvider"""
    mock_session_manager = Mock()
    return HistoryProvider(session_manager=mock_session_manager)


@pytest.fixture
def integrated_builder(real_metadata_builder, real_media_recognizer, real_history_provider):
    """创建完整集成的 ContextBuilder"""
    return ContextBuilder(
        metadata_builder=real_metadata_builder,
        media_recognizer=real_media_recognizer,
        history_provider=real_history_provider
    )


@pytest.fixture
def sample_message():
    """创建示例消息"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.MESSAGE,
        sender_id="123456",
        sender_name="Alice",
        text="你好",
        message_id="msg_001",
        group_id="789",
        group_name="测试群",
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
async def test_end_to_end_text_only(integrated_builder, sample_message):
    """端到端测试：纯文本消息"""
    result = await integrated_builder.build_input(
        sample_message,
        platform_name="qq"
    )

    # 验证所有关键段落存在
    assert "[当前时间]" in result
    assert "[消息元数据]" in result
    assert "- 消息ID: msg_001" in result
    assert "- 发送者: Alice" in result
    assert "usr_" in result  # ID已脱敏
    assert "- 群组: 测试群" in result
    assert "grp_" in result
    assert "[环境信息]" in result
    assert "- 平台: qq" in result
    assert "- 类型: 群聊" in result
    assert "## 当前消息" in result
    assert "你好" in result


@pytest.mark.asyncio
async def test_end_to_end_with_images(integrated_builder, sample_message, mock_vlm):
    """端到端测试：带图片的消息"""
    sample_message.images = ["/local/cat.jpg"]

    with patch('pathlib.Path.is_file', return_value=True):
        result = await integrated_builder.build_input(
            sample_message,
            platform_name="qq"
        )

    assert "[图片识别结果]" in result
    assert "一只猫" in result
    mock_vlm.chat_with_image.assert_called_once()


@pytest.mark.asyncio
async def test_end_to_end_with_history(integrated_builder, sample_message):
    """端到端测试：带历史上下文"""
    context_buffer = {
        "789": [
            {"sender": "Bob", "text": "早上好", "time": "09:00", "images": [], "files": []},
            {"sender": "Charlie", "text": "大家好", "time": "09:05", "images": [], "files": []},
            {"sender": "Alice", "text": "你好", "time": "09:10", "images": [], "files": []},
        ]
    }

    result = await integrated_builder.build_input(
        sample_message,
        platform_name="qq",
        context_buffer=context_buffer,
        window=5
    )

    assert "以下是最近的聊天记录：" in result
    assert "[Bob] 早上好" in result
    assert "[Charlie] 大家好" in result
    # 当前消息不应在历史中
    assert result.count("你好") == 1  # 只在 "## 当前消息" 出现


@pytest.mark.asyncio
async def test_end_to_end_pure_image_with_history(integrated_builder, sample_message, mock_vlm):
    """端到端测试：问题#8 - 纯图消息带历史"""
    sample_message.text = ""  # 纯图消息
    sample_message.images = ["/local/cat.jpg"]

    context_buffer = {
        "789": [
            {"sender": "Bob", "text": "发张照片看看", "time": "09:00", "images": [], "files": []},
            {"sender": "Alice", "text": "", "time": "09:01", "images": ["cat.jpg"], "files": []},
        ]
    }

    with patch('pathlib.Path.is_file', return_value=True):
        result = await integrated_builder.build_input(
            sample_message,
            platform_name="qq",
            context_buffer=context_buffer,
            window=5
        )

    # 验证历史上下文被正确加载
    assert "[Bob] 发张照片看看" in result
    # 验证图片识别正常
    assert "[图片识别结果]" in result
    assert "一只猫" in result


@pytest.mark.asyncio
async def test_end_to_end_complex_message(integrated_builder, sample_message):
    """端到端测试：复杂消息（@、回复、文件）"""
    sample_message.at_targets = ["Bob"]
    sample_message.reply_to = "msg_000"
    sample_message.reply_text = "什么事？"

    mock_file = Mock()
    mock_file.name = "report.pdf"
    sample_message.files = [mock_file]
    sample_message.voices = ["voice.amr"]

    result = await integrated_builder.build_input(
        sample_message,
        platform_name="qq"
    )

    # 验证 @ 和回复
    assert "[At Bob]" in result
    assert "[回复: 什么事？]" in result

    # 验证附件信息
    assert "[附件信息]" in result
    assert "- 文件: 1 个 (report.pdf)" in result
    assert "- 语音消息: 1 条" in result


@pytest.mark.asyncio
async def test_end_to_end_private_chat(integrated_builder):
    """端到端测试：私聊消息"""
    private_msg = ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.MESSAGE,
        sender_id="123456",
        sender_name="Alice",
        text="私聊消息",
        message_id="msg_002",
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

    result = await integrated_builder.build_input(
        private_msg,
        platform_name="qq"
    )

    assert "- 类型: 私聊" in result
    assert "群组" not in result


@pytest.mark.asyncio
async def test_end_to_end_persistence_mode(integrated_builder, sample_message):
    """端到端测试：持久化模式（不加载缓冲区历史）"""
    context_buffer = {
        "789": [
            {"sender": "Bob", "text": "消息1", "time": "09:00", "images": [], "files": []},
            {"sender": "Alice", "text": "你好", "time": "09:01", "images": [], "files": []},
        ]
    }

    result = await integrated_builder.build_input(
        sample_message,
        platform_name="qq",
        context_buffer=context_buffer,
        persistence_enabled=True,
        session_enabled=True
    )

    # 持久化模式下不应加载缓冲区历史
    assert "以下是最近的聊天记录：" not in result
    assert "[Bob] 消息1" not in result
