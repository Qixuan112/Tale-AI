"""
pytest配置文件

提供全局fixture和测试环境配置
"""
import sys
from pathlib import Path
import pytest

# 确保可以导入core模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def mock_config_loader():
    """模拟配置加载器"""
    class MockConfig:
        def get(self, key, default=None):
            return default

        def _load_yaml(self, path):
            return {}

    return MockConfig()


@pytest.fixture
def mock_event_bus():
    """模拟事件总线"""
    class MockEventBus:
        def __init__(self):
            self.events = []
            self.async_events = []

        def emit(self, event_name, data):
            self.events.append((event_name, data))

        async def aemit(self, event_name, data):
            self.async_events.append((event_name, data))

        def on(self, event_name, handler):
            pass

        def clear(self):
            self.events.clear()
            self.async_events.clear()

    return MockEventBus()


@pytest.fixture
def sample_platform_event():
    """创建示例平台事件"""
    from core.adapter.event import PlatformEvent, PlatformType, EventType, SenderInfo, MessageContent
    from datetime import datetime

    return PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.GROUP_MESSAGE,
        sender=SenderInfo(id="123456", name="TestUser", avatar=None, is_bot=False),
        content=MessageContent(text="Hello World", images=[], at_targets=[]),
        message_id="msg_001",
        group_id="group_001",
        group_name="TestGroup",
        timestamp=datetime.now(),
        raw_event={"test": "data"}
    )
