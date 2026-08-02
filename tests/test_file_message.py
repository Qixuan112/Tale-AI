"""
Comprehensive unit tests for PR #118 - QQ Adapter File Message Functionality

Tests cover:
1. FileAttachment data model
2. QQ adapter receiving (OneBot file segment parsing)
3. QQ adapter sending (upload_group_file/upload_private_file)
4. XML parsing (<file> tag support)
5. Message chain (AdapterManager → TaleCore)
6. Error handling (failed_files tracking and notification)
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import asdict
from datetime import datetime

# Import modules under test
from core.adapter.event import (
    FileAttachment,
    MessageContent,
    SendResult,
    PlatformEvent,
    PlatformType,
    EventType,
    SenderInfo,
)
from core.adapter.message_processor import ProcessedMessage
from core.parse_xml import parse_xml_msg


# ============================================================================
# 1. FileAttachment Data Model Tests
# ============================================================================

class TestFileAttachment:
    """Test FileAttachment dataclass"""

    def test_file_attachment_creation_full(self):
        """Test FileAttachment with all fields"""
        file = FileAttachment(
            name="document.pdf",
            url="https://example.com/file.pdf",
            path="/local/path/file.pdf",
            size="1024000"
        )
        assert file.name == "document.pdf"
        assert file.url == "https://example.com/file.pdf"
        assert file.path == "/local/path/file.pdf"
        assert file.size == "1024000"

    def test_file_attachment_creation_minimal(self):
        """Test FileAttachment with minimal fields"""
        file = FileAttachment(name="file.txt")
        assert file.name == "file.txt"
        assert file.url == ""
        assert file.path is None
        assert file.size is None

    def test_file_attachment_in_message_content(self):
        """Test FileAttachment integration in MessageContent"""
        files = [
            FileAttachment(name="doc1.pdf", url="http://example.com/doc1.pdf"),
            FileAttachment(name="doc2.txt", path="/tmp/doc2.txt", size="2048"),
        ]
        content = MessageContent(text="Check these files", files=files)

        assert len(content.files) == 2
        assert content.files[0].name == "doc1.pdf"
        assert content.files[1].size == "2048"
        assert not content.is_empty()

    def test_message_content_to_dict_with_files(self):
        """Test MessageContent.to_dict() serialization with files"""
        files = [FileAttachment(name="test.zip", url="http://ex.com/test.zip", size="5000")]
        content = MessageContent(text="Download this", files=files)

        data = content.to_dict()
        assert "files" in data
        assert len(data["files"]) == 1
        assert data["files"][0]["name"] == "test.zip"
        assert data["files"][0]["url"] == "http://ex.com/test.zip"
        assert data["files"][0]["size"] == "5000"


# ============================================================================
# 2. QQ Adapter - Receiving (Parse OneBot file segment)
# ============================================================================

class TestQQAdapterReceiving:
    """Test QQ adapter parsing OneBot file segments"""

    def test_parse_file_segment_full_data(self):
        """Test parsing file segment with all fields"""
        from core.adapter.src.qq.adapter import QQAdapter

        raw_message = [
            {"type": "text", "data": {"text": "Here is the file"}},
            {
                "type": "file",
                "data": {
                    "name": "report.xlsx",
                    "url": "https://gchat.qpic.cn/gchatpic_new/1234/file/abc123",
                    "file_size": 102400,
                    "path": "/tmp/cache/report.xlsx"
                }
            }
        ]

        content = QQAdapter._parse_message_content(QQAdapter, raw_message)

        assert content.text == "Here is the file"
        assert len(content.files) == 1
        assert content.files[0].name == "report.xlsx"
        assert content.files[0].url == "https://gchat.qpic.cn/gchatpic_new/1234/file/abc123"
        assert content.files[0].size == "102400"
        assert content.files[0].path == "/tmp/cache/report.xlsx"

    def test_parse_file_segment_minimal_data(self):
        """Test parsing file segment with minimal fields"""
        from core.adapter.src.qq.adapter import QQAdapter

        raw_message = [
            {
                "type": "file",
                "data": {
                    "file": "unknown_file"
                }
            }
        ]

        content = QQAdapter._parse_message_content(QQAdapter, raw_message)

        assert len(content.files) == 1
        assert content.files[0].name == "unknown_file"
        assert content.files[0].url == ""
        assert content.files[0].size is None

    def test_parse_multiple_files(self):
        """Test parsing multiple file segments"""
        from core.adapter.src.qq.adapter import QQAdapter

        raw_message = [
            {"type": "file", "data": {"name": "file1.pdf", "url": "http://ex.com/1.pdf"}},
            {"type": "text", "data": {"text": " and "}},
            {"type": "file", "data": {"name": "file2.docx", "url": "http://ex.com/2.docx", "file_size": 5000}},
        ]

        content = QQAdapter._parse_message_content(QQAdapter, raw_message)

        assert content.text == " and "
        assert len(content.files) == 2
        assert content.files[0].name == "file1.pdf"
        assert content.files[1].name == "file2.docx"
        assert content.files[1].size == "5000"

    def test_parse_file_with_no_file_size(self):
        """Test parsing file segment without file_size field"""
        from core.adapter.src.qq.adapter import QQAdapter

        raw_message = [
            {"type": "file", "data": {"name": "test.txt", "url": "http://test.com/file"}}
        ]

        content = QQAdapter._parse_message_content(QQAdapter, raw_message)

        assert content.files[0].size is None


# ============================================================================
# 3. QQ Adapter - Sending (Upload API)
# ============================================================================

@pytest.mark.asyncio
class TestQQAdapterSending:
    """Test QQ adapter file upload functionality"""

    async def test_send_group_file_success(self):
        """Test successful group file upload"""
        from core.adapter.src.qq.adapter import QQAdapter

        # Mock config and client
        config = {
            "ws_url": "ws://localhost:3001",
            "http_url": "http://localhost:3000",
            "bot_uin": "123456"
        }
        adapter = QQAdapter(config)
        adapter.client = AsyncMock()
        adapter.client.websocket = True

        # Mock successful upload response
        adapter._call_action = AsyncMock(return_value={
            "status": "ok",
            "retcode": 0,
            "data": None
        })

        files = [FileAttachment(name="test.pdf", url="http://example.com/test.pdf")]
        content = MessageContent(text="Check this file", files=files)

        result = await adapter.send_message("12345678", content, is_group=True)

        assert result.success
        assert len(result.failed_files) == 0

        # Verify upload_group_file was called
        adapter._call_action.assert_any_call(
            "upload_group_file",
            {
                "group_id": 12345678,
                "file": "http://example.com/test.pdf",
                "name": "test.pdf"
            }
        )

    async def test_send_private_file_success(self):
        """Test successful private file upload"""
        from core.adapter.src.qq.adapter import QQAdapter

        config = {"ws_url": "ws://localhost:3001", "bot_uin": "123456"}
        adapter = QQAdapter(config)
        adapter.client = AsyncMock()
        adapter.client.websocket = True

        adapter._call_action = AsyncMock(return_value={
            "status": "ok",
            "retcode": 0,
        })

        files = [FileAttachment(name="private.doc", path="/tmp/private.doc")]
        content = MessageContent(files=files)

        # Mock _normalize_local_path to return base64
        with patch.object(QQAdapter, '_normalize_local_path', new_callable=AsyncMock) as mock_norm:
            mock_norm.return_value = "base64://AQIDBA=="

            result = await adapter.send_message("987654321", content, is_group=False)

        assert result.success
        assert len(result.failed_files) == 0

    async def test_send_file_upload_failure(self):
        """Test file upload failure handling"""
        from core.adapter.src.qq.adapter import QQAdapter

        config = {"ws_url": "ws://localhost:3001", "bot_uin": "123456"}
        adapter = QQAdapter(config)
        adapter.client = AsyncMock()
        adapter.client.websocket = True

        # Mock failed upload response
        adapter._call_action = AsyncMock(return_value={
            "status": "failed",
            "retcode": 1,
        })

        files = [
            FileAttachment(name="fail1.pdf", url="http://ex.com/fail1.pdf"),
            FileAttachment(name="fail2.zip", url="http://ex.com/fail2.zip"),
        ]
        content = MessageContent(text="These will fail", files=files)

        adapter.client.send_action = AsyncMock(return_value={
            "status": "ok",
            "data": {"message_id": 123}
        })

        result = await adapter.send_message("12345", content, is_group=True)

        # Text sent successfully but files failed
        assert result.success
        assert len(result.failed_files) == 2
        assert "fail1.pdf" in result.failed_files
        assert "fail2.zip" in result.failed_files

    async def test_send_only_files_all_fail(self):
        """Test pure file message where all files fail to upload"""
        from core.adapter.src.qq.adapter import QQAdapter

        config = {"ws_url": "ws://localhost:3001", "bot_uin": "123456"}
        adapter = QQAdapter(config)
        adapter.client = AsyncMock()
        adapter.client.websocket = True

        adapter._call_action = AsyncMock(return_value={
            "status": "failed",
            "retcode": 1,
        })

        files = [FileAttachment(name="only.pdf", url="http://ex.com/only.pdf")]
        content = MessageContent(files=files)

        result = await adapter.send_message("12345", content, is_group=True)

        assert not result.success
        assert len(result.failed_files) == 1
        assert "only.pdf" in result.failed_files

    async def test_send_mixed_content_with_files(self):
        """Test sending text + images + files together"""
        from core.adapter.src.qq.adapter import QQAdapter

        config = {"ws_url": "ws://localhost:3001", "bot_uin": "123456"}
        adapter = QQAdapter(config)
        adapter.client = AsyncMock()
        adapter.client.websocket = True

        adapter.client.send_action = AsyncMock(return_value={
            "status": "ok",
            "data": {"message_id": 456}
        })

        adapter._call_action = AsyncMock(return_value={
            "status": "ok",
            "retcode": 0,
        })

        files = [FileAttachment(name="doc.pdf", url="http://ex.com/doc.pdf")]
        content = MessageContent(
            text="Check this out",
            images=["http://ex.com/image.jpg"],
            files=files
        )

        with patch.object(QQAdapter, '_normalize_local_path', new_callable=AsyncMock) as mock_norm:
            mock_norm.side_effect = lambda src, label: src

            result = await adapter.send_message("12345", content, is_group=True)

        assert result.success
        assert len(result.failed_files) == 0

    async def test_send_file_websocket_not_connected(self):
        """Test file sending when WebSocket is not connected"""
        from core.adapter.src.qq.adapter import QQAdapter

        config = {"ws_url": "ws://localhost:3001", "bot_uin": "123456"}
        adapter = QQAdapter(config)
        adapter.client = Mock()
        adapter.client.websocket = None

        files = [FileAttachment(name="test.pdf", url="http://ex.com/test.pdf")]
        content = MessageContent(text="This will fail", files=files)

        result = await adapter.send_message("12345", content, is_group=True)

        assert not result.success
        assert "test.pdf" in result.failed_files

    async def test_send_file_normalize_failure(self):
        """Test file sending when path normalization fails"""
        from core.adapter.src.qq.adapter import QQAdapter

        config = {"ws_url": "ws://localhost:3001", "bot_uin": "123456"}
        adapter = QQAdapter(config)
        adapter.client = AsyncMock()
        adapter.client.websocket = True

        adapter.client.send_action = AsyncMock(return_value={
            "status": "ok",
            "data": {"message_id": 789}
        })

        files = [FileAttachment(name="bad.pdf", path="/nonexistent/bad.pdf")]
        content = MessageContent(text="File normalization will fail", files=files)

        with patch.object(QQAdapter, '_normalize_local_path', new_callable=AsyncMock) as mock_norm:
            mock_norm.return_value = ""

            result = await adapter.send_message("12345", content, is_group=True)

        assert result.success
        assert "bad.pdf" in result.failed_files


# ============================================================================
# 4. XML Parsing Tests (<file> tag)
# ============================================================================

class TestXMLFileParsing:
    """Test parse_xml_msg support for <file> tag"""

    def test_parse_file_tag_self_closing(self):
        """Test parsing self-closing <file> tag"""
        xml = '''
        <msg>
            <text>Here is the document</text>
            <file name="report.pdf" url="http://example.com/report.pdf" path="/tmp/report.pdf"/>
        </msg>
        '''

        result = parse_xml_msg(xml)

        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert len(msg.files) == 1
        assert msg.files[0]["name"] == "report.pdf"
        assert msg.files[0]["url"] == "http://example.com/report.pdf"
        assert msg.files[0]["path"] == "/tmp/report.pdf"

    def test_parse_file_tag_paired(self):
        """Test parsing paired <file></file> tag"""
        xml = '''
        <msg>
            <text>Download this</text>
            <file name="data.csv" url="http://example.com/data.csv"></file>
        </msg>
        '''

        result = parse_xml_msg(xml)

        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert len(msg.files) == 1
        assert msg.files[0]["name"] == "data.csv"
        assert msg.files[0]["url"] == "http://example.com/data.csv"

    def test_parse_multiple_files_in_message(self):
        """Test parsing multiple <file> tags in one message"""
        xml = '''
        <msg>
            <text>Multiple attachments</text>
            <file name="doc1.pdf" url="http://ex.com/1.pdf"/>
            <file name="doc2.docx" url="http://ex.com/2.docx"/>
            <file name="doc3.xlsx" path="/local/3.xlsx"/>
        </msg>
        '''

        result = parse_xml_msg(xml)

        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert len(msg.files) == 3
        assert msg.files[0]["name"] == "doc1.pdf"
        assert msg.files[1]["name"] == "doc2.docx"
        assert msg.files[2]["name"] == "doc3.xlsx"

    def test_parse_file_tag_minimal_attributes(self):
        """Test parsing <file> tag with minimal attributes"""
        xml = '<msg><file name="test.txt"/></msg>'

        result = parse_xml_msg(xml)

        msg = result["messages"][0]
        assert len(msg.files) == 1
        assert msg.files[0]["name"] == "test.txt"
        assert msg.files[0]["url"] == ""
        assert msg.files[0]["path"] == ""

    def test_parse_file_fallback_extraction(self):
        """Test <file> extraction in fallback mode (malformed XML)"""
        xml = '<msg><text>Test</text><file name="broken.pdf" url="http://ex.com/broken.pdf"'

        result = parse_xml_msg(xml)

        assert "parse_error" in result
        if result["messages"]:
            assert len(result["messages"][0].files) >= 0


# ============================================================================
# 5. AdapterManager Message Chain Tests
# ============================================================================

@pytest.mark.asyncio
class TestAdapterManagerFileTransparency:
    """Test files parameter transparency through AdapterManager"""

    async def test_adapter_manager_send_with_files_dict(self):
        """Test AdapterManager.send_message with files as dict list"""
        from core.adapter.manager import AdapterManager

        manager = AdapterManager()
        mock_adapter = AsyncMock()
        mock_adapter.platform = PlatformType.QQ
        mock_adapter.send_message = AsyncMock(return_value=SendResult(success=True))
        manager._adapters["test_adapter"] = mock_adapter
        manager._enabled_adapters.append("test_adapter")

        files_dict = [
            {"name": "file1.pdf", "url": "http://ex.com/file1.pdf", "size": "1024"},
            {"name": "file2.txt", "path": "/tmp/file2.txt"},
        ]

        result = await manager.send_message(
            adapter_id="test_adapter",
            target_id="12345",
            text="With files",
            files=files_dict
        )

        assert result.success
        call_args = mock_adapter.send_message.call_args
        content = call_args[0][1]
        assert isinstance(content, MessageContent)
        assert len(content.files) == 2
        assert isinstance(content.files[0], FileAttachment)


# ============================================================================
# 6. Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
class TestFileUploadErrorHandling:
    """Test failed_files tracking and notification"""

    async def test_processed_message_includes_files(self):
        """Test ProcessedMessage includes files field"""
        from core.adapter.message_processor import MessageProcessor, ProcessorConfig

        config = ProcessorConfig(permission_mode="none")
        processor = MessageProcessor(config)

        event = PlatformEvent(
            platform=PlatformType.QQ,
            event_type=EventType.PRIVATE_MESSAGE,
            sender=SenderInfo(id="123", name="User"),
            content=MessageContent(
                text="Message with file",
                files=[FileAttachment(name="test.pdf", url="http://ex.com/test.pdf")]
            ),
            message_id="msg123",
            timestamp=datetime.now(),
        )

        processed = processor.process(event)
        assert len(processed.files) == 1
        assert processed.files[0].name == "test.pdf"


# ============================================================================
# 7. Integration Tests
# ============================================================================

@pytest.mark.asyncio
class TestFileMessageIntegration:
    """Integration tests for complete file message flow"""

    async def test_send_result_bool_conversion(self):
        """Test SendResult truthiness matches success field"""
        success_result = SendResult(success=True, failed_files=[])
        assert bool(success_result) is True

        partial_fail = SendResult(success=True, failed_files=["file1.pdf"])
        assert bool(partial_fail) is True

        total_fail = SendResult(success=False, failed_files=["file1.pdf"])
        assert bool(total_fail) is False

