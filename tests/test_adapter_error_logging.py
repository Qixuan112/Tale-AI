"""
Unit tests for Issue #166: Verify error scenarios use logger.error

This test suite verifies that all 13 identified error logging scenarios
use logger.error instead of logger.info.

Test locations:
1. core/adapter/src/websocket/adapter.py: lines 108, 150, 152, 183, 282
2. core/adapter/integration.py: lines 81, 161, 163
3. core/adapter/base.py: line 154
4. core/adapter/manager.py: lines 100, 109, 165
5. core/adapter/src/qq/adapter.py: line 439
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, MagicMock, AsyncMock, patch, mock_open
from datetime import datetime


class TestWebSocketAdapterErrorLogging:
    """Test WebSocket adapter error logging scenarios"""

    @pytest.mark.asyncio
    async def test_websocket_connection_failed_uses_error_log(self):
        """Line 108: Connection failure should use logger.error"""
        with patch('core.adapter.src.websocket.adapter.websockets') as mock_ws, \
             patch('core.adapter.src.websocket.adapter.logger') as mock_logger:

            # Setup: Make connection fail
            mock_ws.connect = AsyncMock(side_effect=Exception("Connection refused"))

            from core.adapter.src.websocket.adapter import WebSocketAdapter

            config = {
                "mode": "client",
                "url": "ws://localhost:8080/ws",
                "auto_reconnect": False
            }
            adapter = WebSocketAdapter(config)
            adapter._running = True
            adapter.url = config["url"]
            adapter.auto_reconnect = config["auto_reconnect"]

            # Trigger connection failure
            await adapter._connect()

            # Assert: Should call logger.error, not logger.info
            # Currently calls logger.info (line 108) - should be logger.error
            assert mock_logger.info.call_count > 0 or mock_logger.error.call_count > 0
            error_logged = any("Connection failed" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Connection failed" in str(call) for call in mock_logger.info.call_args_list)

            # Test will pass when logger.error is used instead of logger.info
            assert error_logged and not info_logged, "Connection failure should use logger.error, not logger.info"

    @pytest.mark.asyncio
    async def test_websocket_invalid_json_uses_error_log(self):
        """Line 150: Invalid JSON should use logger.error"""
        with patch('core.adapter.src.websocket.adapter.logger') as mock_logger, \
             patch('core.adapter.src.websocket.adapter.websockets'):
            from core.adapter.src.websocket.adapter import WebSocketAdapter

            config = {"mode": "server"}
            adapter = WebSocketAdapter(config)
            adapter._clients = {}

            # Create async generator for websocket messages
            async def message_generator():
                yield "invalid json"

            # Create mock websocket with invalid JSON
            mock_ws = AsyncMock()
            mock_ws.remote_address = ("127.0.0.1", 12345)
            mock_ws.__aiter__ = lambda self: message_generator()

            # Trigger invalid JSON handling
            await adapter._handle_client(mock_ws)

            # Assert: Should call logger.error for invalid JSON
            # Currently calls logger.info (line 150) - should be logger.error
            error_logged = any("Invalid JSON" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Invalid JSON" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "Invalid JSON should use logger.error, not logger.info"

    @pytest.mark.asyncio
    async def test_websocket_message_handling_error_uses_error_log(self):
        """Line 152: Message handling error should use logger.error"""
        with patch('core.adapter.src.websocket.adapter.logger') as mock_logger, \
             patch('core.adapter.src.websocket.adapter.websockets'):
            from core.adapter.src.websocket.adapter import WebSocketAdapter

            config = {"mode": "server"}
            adapter = WebSocketAdapter(config)
            adapter._clients = {}
            adapter.emit_event = AsyncMock(side_effect=Exception("Processing error"))

            # Create async generator for websocket messages
            async def message_generator():
                yield json.dumps({"type": "message", "text": "test"})

            # Create mock websocket with valid JSON that causes processing error
            mock_ws = AsyncMock()
            mock_ws.remote_address = ("127.0.0.1", 12345)
            mock_ws.__aiter__ = lambda self: message_generator()

            # Trigger error in message handling
            await adapter._handle_client(mock_ws)

            # Assert: Should call logger.error
            # Currently calls logger.info (line 152) - should be logger.error
            error_logged = any("Error handling message" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Error handling message" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "Message handling error should use logger.error, not logger.info"

    @pytest.mark.asyncio
    async def test_websocket_receive_loop_error_uses_error_log(self):
        """Line 183: Receive loop error should use logger.error"""
        import websockets.exceptions as ws_exceptions

        with patch('core.adapter.src.websocket.adapter.websockets') as mock_ws, \
             patch('core.adapter.src.websocket.adapter.logger') as mock_logger:
            # Point the mock's exceptions attribute at the real module so the
            # `except websockets.exceptions.ConnectionClosed:` clause evaluates
            # to a real exception class (a bare Mock would raise TypeError)
            mock_ws.exceptions = ws_exceptions

            from core.adapter.src.websocket.adapter import WebSocketAdapter

            config = {"mode": "client", "auto_reconnect": False}
            adapter = WebSocketAdapter(config)
            adapter._running = True
            adapter.auto_reconnect = False
            adapter._ws = AsyncMock()
            adapter._ws.recv = AsyncMock(side_effect=Exception("Recv error"))

            # Trigger receive loop error - run briefly then stop
            loop_task = asyncio.create_task(adapter._receive_loop())
            await asyncio.sleep(0.2)
            adapter._running = False

            try:
                await asyncio.wait_for(loop_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

            # Assert: Should call logger.error
            error_logged = any("Error in receive loop" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Error in receive loop" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "Receive loop error should use logger.error, not logger.info"

    @pytest.mark.asyncio
    async def test_websocket_send_message_failure_uses_error_log(self):
        """Line 282: Send message failure should use logger.error"""
        with patch('core.adapter.src.websocket.adapter.logger') as mock_logger:
            from core.adapter.src.websocket.adapter import WebSocketAdapter
            from core.adapter.event import MessageContent

            config = {"mode": "client"}
            adapter = WebSocketAdapter(config)
            adapter.mode = "client"
            adapter._ws = AsyncMock()
            adapter._ws.send = AsyncMock(side_effect=Exception("Send failed"))

            content = MessageContent(text="test")

            # Trigger send failure
            result = await adapter.send_message("target", content)

            # Assert: Should call logger.error and return SendResult(success=False)
            assert result.success is False
            error_logged = any("Failed to send message" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Failed to send message" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "Send message failure should use logger.error, not logger.info"


class TestAdapterIntegrationErrorLogging:
    """Test AdapterEventBridge error logging scenarios"""

    @pytest.mark.asyncio
    async def test_bridge_emit_event_error_uses_error_log(self):
        """Line 81: Event emission error should use logger.error"""
        with patch('core.adapter.integration.logger') as mock_logger:
            from core.adapter.integration import AdapterEventBridge

            # Mock bus without aemit: the sync emit() path runs inside
            # _emit_to_bus's try/except, so its exception is caught there
            mock_bus = Mock()
            mock_bus.emit = Mock(side_effect=Exception("Bus error"))

            bridge = AdapterEventBridge(mock_bus)

            # Trigger event emission error
            bridge._emit_to_bus("test_event", {"data": "test"})

            # Assert: Should call logger.error
            error_logged = any("Error emitting event" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Error emitting event" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "Event emission error should use logger.error, not logger.info"

    @pytest.mark.asyncio
    async def test_bridge_start_adapter_failure_uses_error_log(self):
        """Line 161: Adapter start failure should use logger.error"""
        with patch('core.adapter.integration.logger') as mock_logger:
            from core.adapter.integration import AdapterEventBridge

            bridge = AdapterEventBridge(Mock())
            bridge.manager = Mock()
            bridge.manager.start_adapter = AsyncMock(return_value=False)

            # Trigger adapter start failure
            await bridge._start_adapter_async("test_adapter", {}, "test")

            # Assert: Should call logger.error
            # Currently calls logger.info (line 161) - should be logger.error
            error_logged = any("Failed to start" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Failed to start" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "Adapter start failure should use logger.error, not logger.info"

    @pytest.mark.asyncio
    async def test_bridge_start_adapter_exception_uses_error_log(self):
        """Line 163: Adapter start exception should use logger.error"""
        with patch('core.adapter.integration.logger') as mock_logger:
            from core.adapter.integration import AdapterEventBridge

            bridge = AdapterEventBridge(Mock())
            bridge.manager = Mock()
            bridge.manager.start_adapter = AsyncMock(side_effect=Exception("Start error"))

            # Trigger adapter start exception
            await bridge._start_adapter_async("test_adapter", {}, "test")

            # Assert: Should call logger.error
            # Currently calls logger.info (line 163) - should be logger.error
            error_logged = any("Error starting" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Error starting" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "Adapter start exception should use logger.error, not logger.info"


class TestBaseAdapterErrorLogging:
    """Test BaseAdapter error logging scenarios"""

    def test_base_adapter_on_error_uses_error_log(self):
        """Line 154: on_error callback should use logger.error"""
        with patch('core.adapter.base.logger') as mock_logger:
            from core.adapter.base import BaseAdapter
            from core.adapter.event import PlatformType

            # Create concrete implementation for testing
            class TestAdapter(BaseAdapter):
                @property
                def platform(self):
                    return PlatformType.QQ

                async def start(self):
                    pass

                async def stop(self):
                    pass

                async def send_message(self, target_id, content):
                    pass

                async def parse_event(self, raw_event):
                    pass

            adapter = TestAdapter({})

            # Trigger error callback
            adapter.on_error("Test error message")

            # Assert: Should call logger.error, not logger.info
            # Currently calls logger.info (line 154) - should be logger.error
            error_logged = any("Adapter error" in str(call) and "Test error message" in str(call)
                             for call in mock_logger.error.call_args_list)
            info_logged = any("Adapter error" in str(call) and "Test error message" in str(call)
                            for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "BaseAdapter.on_error should use logger.error, not logger.info"


class TestAdapterManagerErrorLogging:
    """Test AdapterManager error logging scenarios"""

    def test_manager_manifest_load_failure_uses_error_log(self):
        """Line 100: Manifest load failure should use logger.error"""
        with patch('core.adapter.manager.logger') as mock_logger:
            from core.adapter.manager import AdapterManager
            from pathlib import Path

            # Reset scanned flag
            AdapterManager._scanned = False

            # Create a mock adapter directory structure
            with patch.object(Path, 'exists', return_value=True), \
                 patch.object(Path, 'is_dir', return_value=True), \
                 patch.object(Path, 'iterdir') as mock_iterdir, \
                 patch('builtins.open', mock_open(read_data='invalid json')):

                mock_dir = Mock(spec=Path)
                mock_dir.name = "test_adapter"
                mock_dir.is_dir.return_value = True

                # __truediv__ is invoked as (self, other); return real Paths
                # whose exists() is governed by the class-level patch above
                def mock_div(self, other):
                    return Path("/fake/path/test_adapter") / other

                mock_dir.__truediv__ = mock_div
                mock_iterdir.return_value = [mock_dir]

                # Trigger manifest load failure
                AdapterManager.scan_adapters(Path("/fake/path"))

                # Assert: Should call logger.error
                # Currently calls logger.info (line 100) - should be logger.error
                error_logged = any("Failed to load manifest" in str(call) for call in mock_logger.error.call_args_list)
                info_logged = any("Failed to load manifest" in str(call) for call in mock_logger.info.call_args_list)

                assert error_logged and not info_logged, "Manifest load failure should use logger.error, not logger.info"

    def test_manager_schema_load_failure_uses_error_log(self):
        """Line 109: Schema load failure should use logger.error"""
        with patch('core.adapter.manager.logger') as mock_logger:
            from core.adapter.manager import AdapterManager
            from pathlib import Path

            # Reset scanned flag
            AdapterManager._scanned = False

            with patch.object(Path, 'exists', return_value=True), \
                 patch.object(Path, 'is_dir', return_value=True), \
                 patch.object(Path, 'iterdir') as mock_iterdir:

                mock_dir = Mock(spec=Path)
                mock_dir.name = "test_adapter"
                mock_dir.is_dir.return_value = True

                # Setup file mocks: return real Paths (exists patched above),
                # so mock_open_impl can dispatch on str(file)
                def path_div(self, other):
                    return Path("/fake/path/test_adapter") / other

                mock_dir.__truediv__ = path_div
                mock_iterdir.return_value = [mock_dir]

                # Mock open to succeed for manifest, fail for schema
                def mock_open_impl(file, *args, **kwargs):
                    if "manifest.json" in str(file):
                        return mock_open(read_data='{"id": "test", "name": "Test"}')()
                    else:
                        return mock_open(read_data='invalid json')()

                with patch('builtins.open', mock_open_impl):
                    AdapterManager.scan_adapters(Path("/fake/path"))

                # Assert: Should call logger.error for schema failure
                # Currently calls logger.info (line 109) - should be logger.error
                error_logged = any("Failed to load schema" in str(call) for call in mock_logger.error.call_args_list)
                info_logged = any("Failed to load schema" in str(call) for call in mock_logger.info.call_args_list)

                assert error_logged and not info_logged, "Schema load failure should use logger.error, not logger.info"

    def test_manager_adapter_load_failure_uses_error_log(self):
        """Line 165: Adapter load failure should use logger.error"""
        with patch('core.adapter.manager.logger') as mock_logger:
            from core.adapter.manager import AdapterManager
            from pathlib import Path

            # Reset scanned flag
            AdapterManager._scanned = False

            with patch.object(Path, 'exists', return_value=True), \
                 patch.object(Path, 'is_dir', return_value=True), \
                 patch.object(Path, 'iterdir') as mock_iterdir:

                mock_dir = Mock(spec=Path)
                mock_dir.name = "test_adapter"
                mock_dir.is_dir.return_value = True

                def path_div(self, other):
                    return Path("/fake/path/test_adapter") / other

                mock_dir.__truediv__ = path_div
                mock_iterdir.return_value = [mock_dir]

                # Mock file operations to trigger import error
                with patch('builtins.open', mock_open(read_data='{"id": "test", "name": "Test"}')), \
                     patch('importlib.util.spec_from_file_location', side_effect=ImportError("Import failed")):

                    AdapterManager.scan_adapters(Path("/fake/path"))

                # Assert: Should call logger.error
                # Currently calls logger.info (line 165) - should be logger.error
                error_logged = any("Failed to load adapter" in str(call) for call in mock_logger.error.call_args_list)
                info_logged = any("Failed to load adapter" in str(call) for call in mock_logger.info.call_args_list)

                assert error_logged and not info_logged, "Adapter load failure should use logger.error, not logger.info"


class TestQQAdapterErrorLogging:
    """Test QQ adapter error logging scenarios"""

    @pytest.mark.asyncio
    async def test_qq_send_message_failure_uses_error_log(self):
        """Line 439: Send message failure should use logger.error"""
        with patch('core.adapter.src.qq.adapter.logger') as mock_logger:
            from core.adapter.src.qq.adapter import QQAdapter
            from core.adapter.event import MessageContent

            config = {
                "ws_url": "ws://localhost:3001",
                "bot_uin": "123456"
            }
            adapter = QQAdapter(config)
            adapter.client = Mock()
            adapter.client.websocket = Mock()
            adapter.client.send_action = AsyncMock(side_effect=Exception("Network error"))

            content = MessageContent(text="test message")

            # Trigger send failure
            result = await adapter.send_message("12345", content, is_group=False)

            # Assert: Should call logger.error and return SendResult(success=False)
            assert result.success is False
            error_logged = any("Failed to send message" in str(call) for call in mock_logger.error.call_args_list)
            info_logged = any("Failed to send message" in str(call) for call in mock_logger.info.call_args_list)

            assert error_logged and not info_logged, "QQ send message failure should use logger.error, not logger.info"


# Test summary fixture
@pytest.fixture(scope="module", autouse=True)
def test_summary():
    """Print test summary"""
    yield
    print("\n" + "="*70)
    print("Issue #166 Error Logging Test Suite Summary")
    print("="*70)
    print("Total test scenarios: 13")
    print("\nTest coverage:")
    print("  • WebSocket adapter: 5 scenarios")
    print("  • Integration bridge: 3 scenarios")
    print("  • Base adapter: 1 scenario")
    print("  • Adapter manager: 3 scenarios")
    print("  • QQ adapter: 1 scenario")
    print("\nAll tests verify that error scenarios call logger.error")
    print("instead of logger.info as required by Issue #166.")
    print("="*70)
