"""
Unit tests for NameMappingStage

Tests nickname to ID mapping maintenance.
"""
import pytest
from unittest.mock import MagicMock
from core.pipeline.stages.name_mapping import NameMappingStage
from core.pipeline.context import PipelineContext
from core.adapter.message_processor import ProcessedMessage
from core.adapter.event import PlatformType
from core.utils.cache import BoundedCache
from core.utils.id_sanitizer import IDSanitizer

@pytest.fixture
def name_cache():
    """Create a name-to-ID cache"""
    return BoundedCache(maxsize=100, ttl=3600)

@pytest.fixture
def id_sanitizer():
    """Create an ID sanitizer"""
    return IDSanitizer()

@pytest.fixture
def stage(name_cache, id_sanitizer):
    """Create NameMappingStage"""
    return NameMappingStage(name_cache, id_sanitizer)

class TestNameMappingStage:
    """Test NameMappingStage"""

    def test_stage_initialization(self, stage):
        """Should initialize with correct order and name"""
        assert stage.order == 200
        assert stage.name == "name_mapping"
        assert stage.always_run is False

    @pytest.mark.asyncio
    async def test_process_stores_name_mapping(self, stage, name_cache, mock_processed):
        """Should store sender name to ID mapping"""
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        # Check mapping was stored for private chat
        name_map = name_cache.get("_private", {})
        assert "TestUser" in name_map
        assert name_map["TestUser"].startswith("usr_")  # Sanitized ID

    @pytest.mark.asyncio
    async def test_process_group_message_mapping(self, stage, name_cache, mock_processed):
        """Should store mapping under group key for group messages"""
        mock_processed.group_id = "group123"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        # Check mapping was stored under group key
        name_map = name_cache.get("group123", {})
        assert "TestUser" in name_map

    @pytest.mark.asyncio
    async def test_process_sanitizes_id(self, stage, name_cache, mock_processed):
        """Should sanitize user ID before storing"""
        mock_processed.sender_id = "12345678"
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        name_map = name_cache.get("_private", {})
        masked_id = name_map["TestUser"]
        # ID should be masked
        assert masked_id != "12345678"
        assert "usr_" in masked_id

    @pytest.mark.asyncio
    async def test_process_updates_existing_mapping(self, stage, name_cache, mock_processed):
        """Should update mapping if name already exists"""
        # Pre-populate cache
        name_cache["_private"] = {"TestUser": "old_id"}

        ctx = PipelineContext(processed=mock_processed)
        await stage.process(ctx)

        name_map = name_cache.get("_private", {})
        # Should be updated, not the old value
        assert name_map["TestUser"] != "old_id"

    @pytest.mark.asyncio
    async def test_process_multiple_names_same_group(self, stage, name_cache):
        """Should store multiple names in same group"""
        # First user
        processed1 = ProcessedMessage(
            platform=PlatformType.QQ,
            sender_id="user1",
            sender_name="Alice",
            text="Hi",
            message_id="msg1",
            group_id="group123",
            group_name=None,
            at_targets=[],
            reply_to=None,
            reply_text=None,
            images=[], files=[], voices=[], faces=[], stickers=[], videos=[],
            is_group_message=True,
            reason="mention",
            decision=None
        )
        ctx1 = PipelineContext(processed=processed1)
        await stage.process(ctx1)

        # Second user
        processed2 = ProcessedMessage(
            platform=PlatformType.QQ,
            sender_id="user2",
            sender_name="Bob",
            text="Hello",
            message_id="msg2",
            group_id="group123",
            group_name=None,
            at_targets=[],
            reply_to=None,
            reply_text=None,
            images=[], files=[], voices=[], faces=[], stickers=[], videos=[],
            is_group_message=True,
            reason="mention",
            decision=None
        )
        ctx2 = PipelineContext(processed=processed2)
        await stage.process(ctx2)

        name_map = name_cache.get("group123", {})
        assert "Alice" in name_map
        assert "Bob" in name_map
        assert len(name_map) == 2

    @pytest.mark.asyncio
    async def test_process_skips_without_sender_name(self, stage, name_cache, mock_processed):
        """Should skip mapping when sender_name is missing"""
        mock_processed.sender_name = None
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        # No mapping should be stored
        assert name_cache.get("_private") is None

    @pytest.mark.asyncio
    async def test_process_skips_without_sender_id(self, stage, name_cache, mock_processed):
        """Should skip mapping when sender_id is missing"""
        mock_processed.sender_id = None
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        # No mapping should be stored
        assert name_cache.get("_private") is None

    @pytest.mark.asyncio
    async def test_process_skips_empty_sender_name(self, stage, name_cache, mock_processed):
        """Should skip mapping when sender_name is empty string"""
        mock_processed.sender_name = ""
        ctx = PipelineContext(processed=mock_processed)

        await stage.process(ctx)

        # No mapping should be stored
        assert name_cache.get("_private") is None

    @pytest.mark.asyncio
    async def test_process_different_groups_separate_mappings(self, stage, name_cache):
        """Should maintain separate mappings for different groups"""
        # Same name in group1
        processed1 = ProcessedMessage(
            platform=PlatformType.QQ,
            sender_id="user1",
            sender_name="Alice",
            text="Hi",
            message_id="msg1",
            group_id="group1",
            group_name=None,
            at_targets=[],
            reply_to=None,
            reply_text=None,
            images=[], files=[], voices=[], faces=[], stickers=[], videos=[],
            is_group_message=True,
            reason="mention",
            decision=None
        )
        ctx1 = PipelineContext(processed=processed1)
        await stage.process(ctx1)

        # Same name in group2 but different ID
        processed2 = ProcessedMessage(
            platform=PlatformType.QQ,
            sender_id="user2",
            sender_name="Alice",
            text="Hello",
            message_id="msg2",
            group_id="group2",
            group_name=None,
            at_targets=[],
            reply_to=None,
            reply_text=None,
            images=[], files=[], voices=[], faces=[], stickers=[], videos=[],
            is_group_message=True,
            reason="mention",
            decision=None
        )
        ctx2 = PipelineContext(processed=processed2)
        await stage.process(ctx2)

        # Both groups should have Alice but with different IDs
        map1 = name_cache.get("group1", {})
        map2 = name_cache.get("group2", {})
        assert "Alice" in map1
        assert "Alice" in map2
        assert map1["Alice"] != map2["Alice"]

    @pytest.mark.asyncio
    async def test_process_private_vs_group_separation(self, stage, name_cache):
        """Should separate private and group mappings"""
        # Private message
        processed_private = ProcessedMessage(
            platform=PlatformType.QQ,
            sender_id="user1",
            sender_name="Alice",
            text="Hi",
            message_id="msg1",
            group_id=None,
            group_name=None,
            at_targets=[],
            reply_to=None,
            reply_text=None,
            images=[], files=[], voices=[], faces=[], stickers=[], videos=[],
            is_group_message=False,
            reason="direct",
            decision=None
        )
        ctx_private = PipelineContext(processed=processed_private)
        await stage.process(ctx_private)

        # Group message
        processed_group = ProcessedMessage(
            platform=PlatformType.QQ,
            sender_id="user1",
            sender_name="Alice",
            text="Hello",
            message_id="msg2",
            group_id="group123",
            group_name=None,
            at_targets=[],
            reply_to=None,
            reply_text=None,
            images=[], files=[], voices=[], faces=[], stickers=[], videos=[],
            is_group_message=True,
            reason="mention",
            decision=None
        )
        ctx_group = PipelineContext(processed=processed_group)
        await stage.process(ctx_group)

        # Should have separate entries
        assert name_cache.get("_private") is not None
        assert name_cache.get("group123") is not None
        assert "Alice" in name_cache.get("_private", {})
        assert "Alice" in name_cache.get("group123", {})

    @pytest.mark.asyncio
    async def test_cache_write_triggers_ttl_update(self, stage, name_cache, mock_processed):
        """Each write should trigger cache __setitem__ to update TTL"""
        ctx = PipelineContext(processed=mock_processed)

        # First write
        await stage.process(ctx)
        first_map = name_cache.get("_private")

        # Second write (should update TTL via __setitem__)
        mock_processed.sender_name = "TestUser2"
        mock_processed.sender_id = "87654321"
        ctx2 = PipelineContext(processed=mock_processed)
        await stage.process(ctx2)

        updated_map = name_cache.get("_private")
        # Should have both entries
        assert "TestUser" in updated_map
        assert "TestUser2" in updated_map
