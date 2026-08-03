"""Unit tests for HistoryProvider

测试历史消息加载：
- 持久化模式 vs 缓冲区模式
- 窗口大小控制
- 消息格式化
- 边界条件
"""

import pytest
from unittest.mock import Mock
from core.chat.context_builder.history_provider import HistoryProvider
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType, EventType


@pytest.fixture
def session_manager():
    """创建 mock SessionManager"""
    return Mock()


@pytest.fixture
def history_provider(session_manager):
    """创建历史提供器"""
    return HistoryProvider(session_manager)


@pytest.fixture
def basic_processed():
    """创建基础 ProcessedMessage"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.MESSAGE,
        sender_id="12345",
        sender_name="TestUser",
        text="Current message",
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
async def test_get_history_persistence_mode(history_provider, basic_processed):
    """测试持久化模式下返回空字符串（历史已通过 set_session 加载）"""
    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=None,
        persistence_enabled=True,
        session_enabled=True
    )

    assert result == ""


@pytest.mark.asyncio
async def test_get_history_no_buffer(history_provider, basic_processed):
    """测试无缓冲区时返回空"""
    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=None,
        persistence_enabled=False,
        session_enabled=False
    )

    assert result == ""


@pytest.mark.asyncio
async def test_get_history_empty_buffer(history_provider, basic_processed):
    """测试空缓冲区返回空"""
    buffer = {}

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    assert result == ""


@pytest.mark.asyncio
async def test_get_history_with_messages(history_provider, basic_processed):
    """测试从缓冲区加载历史消息"""
    buffer = {
        "12345": [
            {"sender": "User1", "text": "Hello", "time": "10:00", "images": [], "files": []},
            {"sender": "User2", "text": "Hi", "time": "10:01", "images": [], "files": []},
            {"sender": "TestUser", "text": "Current message", "time": "10:02", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        window=5,
        persistence_enabled=False,
        session_enabled=False
    )

    assert "---" in result
    assert "以下是最近的聊天记录：" in result
    assert "[User1] Hello" in result
    assert "[User2] Hi" in result
    assert "Current message" not in result  # 当前消息应被排除


@pytest.mark.asyncio
async def test_get_history_window_limit(history_provider, basic_processed):
    """测试窗口大小限制"""
    messages = [
        {"sender": f"User{i}", "text": f"Msg {i}", "time": f"10:{i:02d}",
         "images": [], "files": []}
        for i in range(10)
    ]
    messages.append({"sender": "TestUser", "text": "Current", "time": "10:10",
                    "images": [], "files": []})

    buffer = {"12345": messages}

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        window=3,  # 只取3条
        persistence_enabled=False,
        session_enabled=False
    )

    # 应该只包含最近的3条（排除当前消息）
    lines = result.split('\n')
    message_lines = [l for l in lines if l.startswith('[User')]
    assert len(message_lines) == 3
    assert "[User7]" in result
    assert "[User8]" in result
    assert "[User9]" in result


@pytest.mark.asyncio
async def test_get_history_with_files(history_provider, basic_processed):
    """测试包含文件的消息"""
    buffer = {
        "12345": [
            {
                "sender": "User1",
                "text": "Check this",
                "time": "10:00",
                "images": [],
                "files": [
                    {"name": "doc.pdf", "url": "http://...", "size": 1024},
                    {"name": "image.png", "url": "http://...", "size": 2048}
                ]
            },
            {"sender": "TestUser", "text": "Current", "time": "10:01", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    assert "[User1] Check this [文件: doc.pdf, image.png]" in result


@pytest.mark.asyncio
async def test_get_history_file_only_message(history_provider, basic_processed):
    """测试纯文件消息（无文本）"""
    buffer = {
        "12345": [
            {
                "sender": "User1",
                "text": "",
                "time": "10:00",
                "images": [],
                "files": [{"name": "doc.pdf", "url": "http://...", "size": 1024}]
            },
            {"sender": "TestUser", "text": "Current", "time": "10:01", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    assert "[User1] [文件: doc.pdf]" in result


@pytest.mark.asyncio
async def test_get_history_image_only_message(history_provider, basic_processed):
    """测试纯图片消息"""
    buffer = {
        "12345": [
            {"sender": "User1", "text": "", "time": "10:00", "images": ["img.jpg"], "files": []},
            {"sender": "TestUser", "text": "Current", "time": "10:01", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    assert "[User1] [图片]" in result


@pytest.mark.asyncio
async def test_get_history_group_message(history_provider, basic_processed):
    """测试群聊消息使用 group_id 作为 key"""
    basic_processed.group_id = "67890"

    buffer = {
        "67890": [
            {"sender": "User1", "text": "Group message", "time": "10:00", "images": [], "files": []},
            {"sender": "TestUser", "text": "Current", "time": "10:01", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    assert "[User1] Group message" in result


@pytest.mark.asyncio
async def test_get_history_only_current_message(history_provider, basic_processed):
    """测试缓冲区只有当前消息时返回空"""
    buffer = {
        "12345": [
            {"sender": "TestUser", "text": "Current", "time": "10:01", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    assert result == ""


@pytest.mark.asyncio
async def test_get_history_session_disabled(history_provider, basic_processed):
    """测试会话禁用时仍从缓冲区加载（非持久化模式）"""
    buffer = {
        "12345": [
            {"sender": "User1", "text": "Hello", "time": "10:00", "images": [], "files": []},
            {"sender": "TestUser", "text": "Current", "time": "10:01", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    assert "[User1] Hello" in result


@pytest.mark.asyncio
async def test_get_history_files_limit(history_provider, basic_processed):
    """测试文件数量限制（最多显示3个）"""
    files = [{"name": f"file{i}.txt", "url": "http://...", "size": 1024} for i in range(5)]

    buffer = {
        "12345": [
            {"sender": "User1", "text": "Files", "time": "10:00", "images": [], "files": files},
            {"sender": "TestUser", "text": "Current", "time": "10:01", "images": [], "files": []},
        ]
    }

    result = await history_provider.get_history_context(
        basic_processed,
        context_buffer=buffer,
        persistence_enabled=False,
        session_enabled=False
    )

    # 应该只显示前3个文件名
    assert "file0.txt" in result
    assert "file1.txt" in result
    assert "file2.txt" in result
