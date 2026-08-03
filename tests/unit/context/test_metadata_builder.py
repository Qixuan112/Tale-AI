"""Unit tests for MetadataBuilder

测试元数据构建的各个方面：
- 时间格式
- 消息元数据（ID脱敏）
- 环境信息
- 富媒体信息
- 用户消息格式化
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from core.chat.context_builder.metadata_builder import MetadataBuilder
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType, EventType, MessageContent, SenderInfo
from core.utils.id_sanitizer import IDSanitizer


@pytest.fixture
def id_sanitizer():
    """创建 ID 脱敏器"""
    return IDSanitizer()


@pytest.fixture
def metadata_builder(id_sanitizer):
    """创建元数据构建器"""
    return MetadataBuilder(id_sanitizer)


@pytest.fixture
def basic_processed_message():
    """创建基础的 ProcessedMessage"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.MESSAGE,
        sender_id="12345",
        sender_name="TestUser",
        text="Hello",
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


def test_build_time_section(metadata_builder):
    """测试时间段落构建"""
    with patch('core.chat.context_builder.metadata_builder.datetime') as mock_dt:
        mock_dt.datetime.now.return_value = datetime(2024, 1, 15, 14, 30, 0)
        mock_dt.datetime.strftime = datetime.strftime

        result = metadata_builder._build_time_section()

        assert "[当前时间]" in result
        assert "2024-01-15 14:30" in result


def test_build_message_metadata_private(metadata_builder, basic_processed_message):
    """测试私聊消息元数据"""
    result = metadata_builder._build_message_metadata(basic_processed_message)

    assert "[消息元数据]" in result
    assert "- 消息ID: msg_001" in result
    assert "- 发送者: TestUser" in result
    assert "usr_" in result  # ID已脱敏
    assert "12345" not in result  # 原始ID不应出现


def test_build_message_metadata_group(metadata_builder, basic_processed_message):
    """测试群聊消息元数据"""
    basic_processed_message.group_id = "67890"
    basic_processed_message.group_name = "TestGroup"

    result = metadata_builder._build_message_metadata(basic_processed_message)

    assert "- 群组: TestGroup" in result
    assert "grp_" in result  # 群ID已脱敏
    assert "67890" not in result


def test_build_message_metadata_group_no_name(metadata_builder, basic_processed_message):
    """测试无群名的群聊元数据"""
    basic_processed_message.group_id = "67890"
    basic_processed_message.group_name = None

    result = metadata_builder._build_message_metadata(basic_processed_message)

    assert "- 群组ID:" in result
    assert "grp_" in result


def test_build_environment_info_private(metadata_builder, basic_processed_message):
    """测试私聊环境信息"""
    result = metadata_builder._build_environment_info(basic_processed_message, "qq")

    assert "[环境信息]" in result
    assert "- 平台: qq" in result
    assert "- 类型: 私聊" in result


def test_build_environment_info_group(metadata_builder, basic_processed_message):
    """测试群聊环境信息"""
    basic_processed_message.group_id = "67890"

    result = metadata_builder._build_environment_info(basic_processed_message, "qq")

    assert "- 类型: 群聊" in result


def test_build_media_info_empty(metadata_builder, basic_processed_message):
    """测试无富媒体时返回空字符串"""
    result = metadata_builder._build_media_info(basic_processed_message)

    assert result == ""


def test_build_media_info_with_voices(metadata_builder, basic_processed_message):
    """测试语音消息信息"""
    basic_processed_message.voices = ["voice1.amr", "voice2.amr"]

    result = metadata_builder._build_media_info(basic_processed_message)

    assert "[附件信息]" in result
    assert "- 语音消息: 2 条" in result


def test_build_media_info_with_files(metadata_builder, basic_processed_message):
    """测试文件附件信息"""
    mock_file1 = Mock()
    mock_file1.name = "document.pdf"
    mock_file2 = Mock()
    mock_file2.name = "image.png"

    basic_processed_message.files = [mock_file1, mock_file2]

    result = metadata_builder._build_media_info(basic_processed_message)

    assert "- 文件: 2 个" in result
    assert "document.pdf" in result
    assert "image.png" in result


def test_build_media_info_multiple_types(metadata_builder, basic_processed_message):
    """测试多种富媒体类型"""
    basic_processed_message.voices = ["v1"]
    basic_processed_message.faces = ["f1", "f2"]
    basic_processed_message.stickers = ["s1"]
    basic_processed_message.videos = ["vid1"]

    result = metadata_builder._build_media_info(basic_processed_message)

    assert "- 语音消息: 1 条" in result
    assert "- QQ表情: 2 个" in result
    assert "- 动画表情: 1 个" in result
    assert "- 视频: 1 个" in result


def test_format_user_message_simple(metadata_builder, basic_processed_message):
    """测试简单消息格式化"""
    result = metadata_builder.format_user_message(basic_processed_message)

    assert result == "Hello"


def test_format_user_message_with_at(metadata_builder, basic_processed_message):
    """测试带 @ 的消息"""
    basic_processed_message.at_targets = ["user1", "user2"]

    result = metadata_builder.format_user_message(basic_processed_message)

    assert "[At user1]" in result
    assert "[At user2]" in result
    assert "Hello" in result


def test_format_user_message_with_reply(metadata_builder, basic_processed_message):
    """测试带回复的消息"""
    basic_processed_message.reply_to = "msg_000"
    basic_processed_message.reply_text = "Previous message"

    result = metadata_builder.format_user_message(basic_processed_message)

    assert "[回复: Previous message]" in result
    assert "Hello" in result


def test_format_user_message_with_reply_no_text(metadata_builder, basic_processed_message):
    """测试带回复但无回复文本"""
    basic_processed_message.reply_to = "msg_000"

    result = metadata_builder.format_user_message(basic_processed_message)

    assert "[Reply msg_000]" in result


def test_build_metadata_complete(metadata_builder, basic_processed_message):
    """测试完整元数据构建"""
    mock_file = Mock()
    mock_file.name = "test.pdf"
    basic_processed_message.files = [mock_file]

    with patch.object(metadata_builder, '_build_time_section', return_value="[时间]"):
        result = metadata_builder.build_metadata(
            basic_processed_message,
            "qq",
            "Hello"
        )

    assert "[时间]" in result
    assert "[消息元数据]" in result
    assert "[环境信息]" in result
    assert "[附件信息]" in result
