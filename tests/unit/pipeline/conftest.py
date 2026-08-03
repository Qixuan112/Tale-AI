"""
Shared test fixtures for pipeline tests
"""
import pytest
from core.adapter.message_processor import ProcessedMessage, ResponseDecision
from core.adapter.event import PlatformType, EventType


@pytest.fixture
def mock_processed():
    """Create a basic ProcessedMessage for testing"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.GROUP_MESSAGE,
        message_id="msg001",
        sender_id="user123",
        sender_name="TestUser",
        text="Hello world",
        decision=ResponseDecision.RESPOND,
        reason="wake_word"
    )


@pytest.fixture
def mock_group_processed():
    """Create a group message ProcessedMessage"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.GROUP_MESSAGE,
        message_id="msg001",
        sender_id="user123",
        sender_name="TestUser",
        text="Hello group",
        group_id="group456",
        group_name="Test Group",
        decision=ResponseDecision.RESPOND,
        reason="mention"
    )


@pytest.fixture
def mock_private_processed():
    """Create a private message ProcessedMessage"""
    return ProcessedMessage(
        platform=PlatformType.QQ,
        event_type=EventType.PRIVATE_MESSAGE,
        message_id="msg001",
        sender_id="user123",
        sender_name="TestUser",
        text="Hello",
        decision=ResponseDecision.RESPOND,
        reason="direct"
    )
