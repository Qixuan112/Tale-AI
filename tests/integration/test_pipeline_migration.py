"""
StandardPipeline 灰度迁移集成测试
=================================
验证 Feature Flag 切换时两条路径都能正常工作。
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock

from core.adapter.event import PlatformEvent, PlatformType, EventType, MessageContent, SenderInfo
from core.adapter.message_processor import ProcessedMessage, ResponseDecision


class TestPipelineMigration:
    """Pipeline 灰度迁移测试"""

    def _create_mock_event(self) -> PlatformEvent:
        """创建模拟 PlatformEvent"""
        from datetime import datetime
        return PlatformEvent(
            platform=PlatformType.QQ,
            event_type=EventType.MESSAGE,
            sender=SenderInfo(
                id="12345",
                name="测试用户",
                is_bot=False
            ),
            content=MessageContent(text="你好"),
            group_id=None,
            timestamp=datetime.fromtimestamp(1722758400.0),
            raw_event={}
        )

    def _create_mock_processed(self, event: PlatformEvent) -> ProcessedMessage:
        """创建模拟 ProcessedMessage"""
        return ProcessedMessage(
            decision=ResponseDecision.RESPOND,
            reason="正常响应",
            text="你好",
            sender_id="12345",
            sender_name="测试用户",
            group_id=None,
            platform=PlatformType.QQ
        )

    @pytest.mark.asyncio
    async def test_legacy_path_selected_when_flag_false(self):
        """测试 Feature Flag=false 时选择旧版路径"""
        from core.main import TaleCore
        from core.config.loader import config_loader

        # Mock config to return use_pipeline=False
        with patch.object(config_loader.bot.bot, 'use_pipeline', False):
            core = TaleCore()
            event = self._create_mock_event()
            processed = self._create_mock_processed(event)

            # Mock both handlers to track which is called
            legacy_called = False
            pipeline_called = False

            async def mock_legacy(proc, adapter_instance=None):
                nonlocal legacy_called
                legacy_called = True

            async def mock_pipeline(proc, adapter_instance=None):
                nonlocal pipeline_called
                pipeline_called = True

            core._handle_respond_message = mock_legacy
            core._handle_respond_message_v2 = mock_pipeline

            # Mock message processor
            core.message_processor = Mock()
            core.message_processor.process.return_value = processed

            # Mock _store_to_context_buffer
            core._store_to_context_buffer = Mock()

            # Trigger message processing
            await core._process_message_event(event, adapter_instance="qq")

            # Verify legacy path was called
            assert legacy_called, "Legacy path should be called when use_pipeline=False"
            assert not pipeline_called, "Pipeline path should NOT be called"

    @pytest.mark.asyncio
    async def test_pipeline_path_selected_when_flag_true(self):
        """测试 Feature Flag=true 时选择 Pipeline 路径"""
        from core.main import TaleCore
        from core.config.loader import config_loader

        # Mock config to return use_pipeline=True
        with patch.object(config_loader.bot.bot, 'use_pipeline', True):
            core = TaleCore()
            event = self._create_mock_event()
            processed = self._create_mock_processed(event)

            # Mock both handlers to track which is called
            legacy_called = False
            pipeline_called = False

            async def mock_legacy(proc, adapter_instance=None):
                nonlocal legacy_called
                legacy_called = True

            async def mock_pipeline(proc, adapter_instance=None):
                nonlocal pipeline_called
                pipeline_called = True

            core._handle_respond_message = mock_legacy
            core._handle_respond_message_v2 = mock_pipeline

            # Mock message processor
            core.message_processor = Mock()
            core.message_processor.process.return_value = processed

            # Mock _store_to_context_buffer
            core._store_to_context_buffer = Mock()

            # Trigger message processing
            await core._process_message_event(event, adapter_instance="qq")

            # Verify pipeline path was called
            assert pipeline_called, "Pipeline path should be called when use_pipeline=True"
            assert not legacy_called, "Legacy path should NOT be called"

    @pytest.mark.asyncio
    async def test_logging_includes_path_indicator(self, caplog):
        """测试日志包含路径标识符"""
        from core.main import TaleCore
        from core.config.loader import config_loader
        import logging

        caplog.set_level(logging.INFO)

        # Test legacy path logging
        with patch.object(config_loader.bot.bot, 'use_pipeline', False):
            core = TaleCore()
            event = self._create_mock_event()
            processed = self._create_mock_processed(event)

            # Mock handler to prevent actual execution
            core._handle_respond_message = AsyncMock()
            core.message_processor = Mock()
            core.message_processor.process.return_value = processed
            core._store_to_context_buffer = Mock()

            await core._process_message_event(event, adapter_instance="qq")

            # Check for legacy log
            assert any("[Legacy]" in record.message for record in caplog.records), \
                "Should log [Legacy] indicator"

        caplog.clear()

        # Test pipeline path logging
        with patch.object(config_loader.bot.bot, 'use_pipeline', True):
            core = TaleCore()
            event = self._create_mock_event()
            processed = self._create_mock_processed(event)

            core._handle_respond_message_v2 = AsyncMock()
            core.message_processor = Mock()
            core.message_processor.process.return_value = processed
            core._store_to_context_buffer = Mock()

            await core._process_message_event(event, adapter_instance="qq")

            # Check for pipeline log
            assert any("[Pipeline]" in record.message for record in caplog.records), \
                "Should log [Pipeline] indicator"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
