"""
Unit tests for StandardPipeline

Tests the standard pipeline implementation with event hooks and error recovery.
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, call
from core.pipeline.standard import StandardPipeline
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext
from core.bus import EventBus


class MockStage(PipelineStage):
    """Mock stage for testing"""

    def __init__(self, order, name, always_run=False, should_fail=False, delay=0):
        super().__init__(order, name, always_run)
        self.executed = False
        self.should_fail = should_fail
        self.delay = delay

    async def process(self, ctx):
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        self.executed = True
        ctx.extra.setdefault("execution_log", []).append(self.name)
        if self.should_fail:
            raise RuntimeError(f"{self.name} failed")


class RecoverableStage(PipelineStage):
    """Stage that can recover from errors"""

    def __init__(self, order, name):
        super().__init__(order, name)
        self.executed = False
        self.error_handled = False

    async def process(self, ctx):
        self.executed = True
        raise ValueError("Recoverable error")

    async def on_error(self, ctx, error):
        self.error_handled = True
        ctx.extra["recovered_from"] = self.name
        return True  # Signal recovery


@pytest.fixture
def mock_bus():
    """Mock EventBus for testing"""
    bus = MagicMock(spec=EventBus)
    bus.emit = MagicMock()
    return bus


@pytest.fixture
def mock_context():
    """Create a mock PipelineContext"""
    return PipelineContext(processed=MagicMock())


class TestStandardPipeline:
    """Test StandardPipeline implementation"""

    def test_pipeline_initialization_without_bus(self):
        """Should initialize without event bus"""
        pipeline = StandardPipeline()

        assert pipeline._bus is None
        assert pipeline._stages == []

    def test_pipeline_initialization_with_bus(self, mock_bus):
        """Should initialize with event bus"""
        pipeline = StandardPipeline(bus=mock_bus)

        assert pipeline._bus is mock_bus

    @pytest.mark.asyncio
    async def test_execute_empty_pipeline(self, mock_context):
        """Should handle pipeline with no stages"""
        pipeline = StandardPipeline()

        result = await pipeline.execute(mock_context)

        assert result is mock_context

    @pytest.mark.asyncio
    async def test_execute_single_stage(self, mock_context):
        """Should execute single stage"""
        pipeline = StandardPipeline()
        stage = MockStage(100, "stage1")
        pipeline.add_stage(stage)

        result = await pipeline.execute(mock_context)

        assert stage.executed is True
        assert result.extra["execution_log"] == ["stage1"]

    @pytest.mark.asyncio
    async def test_execute_multiple_stages_in_order(self, mock_context):
        """Should execute stages in order"""
        pipeline = StandardPipeline()
        pipeline.add_stage(MockStage(300, "stage3"))
        pipeline.add_stage(MockStage(100, "stage1"))
        pipeline.add_stage(MockStage(200, "stage2"))

        result = await pipeline.execute(mock_context)

        assert result.extra["execution_log"] == ["stage1", "stage2", "stage3"]

    @pytest.mark.asyncio
    async def test_execute_emits_before_events(self, mock_context, mock_bus):
        """Should emit before_stage events"""
        pipeline = StandardPipeline(bus=mock_bus)
        pipeline.add_stage(MockStage(100, "stage1"))
        pipeline.add_stage(MockStage(200, "stage2"))

        await pipeline.execute(mock_context)

        # Check before events were emitted
        assert any(
            call_args[0][0] == "pipeline_stage_before_stage1"
            for call_args in mock_bus.emit.call_args_list
        )
        assert any(
            call_args[0][0] == "pipeline_stage_before_stage2"
            for call_args in mock_bus.emit.call_args_list
        )

    @pytest.mark.asyncio
    async def test_execute_emits_after_events(self, mock_context, mock_bus):
        """Should emit after_stage events"""
        pipeline = StandardPipeline(bus=mock_bus)
        pipeline.add_stage(MockStage(100, "stage1"))
        pipeline.add_stage(MockStage(200, "stage2"))

        await pipeline.execute(mock_context)

        # Check after events were emitted
        assert any(
            call_args[0][0] == "pipeline_stage_after_stage1"
            for call_args in mock_bus.emit.call_args_list
        )
        assert any(
            call_args[0][0] == "pipeline_stage_after_stage2"
            for call_args in mock_bus.emit.call_args_list
        )

    @pytest.mark.asyncio
    async def test_execute_skips_stages_after_stop(self, mock_context):
        """Should skip stages after should_stop is set"""
        pipeline = StandardPipeline()
        stage1 = MockStage(100, "stage1")
        stage2 = MockStage(200, "stage2")
        stage3 = MockStage(300, "stage3")

        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)
        pipeline.add_stage(stage3)

        # Set stop flag after stage1
        async def stop_after_stage1(ctx):
            ctx.extra.setdefault("execution_log", []).append("stage1")
            ctx.stop()

        stage1.process = stop_after_stage1

        await pipeline.execute(mock_context)

        assert stage1.executed is False  # Overridden
        assert stage2.executed is False  # Skipped
        assert stage3.executed is False  # Skipped
        assert mock_context.extra["execution_log"] == ["stage1"]

    @pytest.mark.asyncio
    async def test_execute_always_run_stages_ignore_stop(self, mock_context):
        """always_run stages should execute even after stop"""
        pipeline = StandardPipeline()
        stage1 = MockStage(100, "stage1")
        stage2 = MockStage(200, "stage2", always_run=False)
        stage3 = MockStage(300, "stage3", always_run=True)

        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)
        pipeline.add_stage(stage3)

        # Set stop after stage1
        async def stop_after_stage1(ctx):
            ctx.extra.setdefault("execution_log", []).append("stage1")
            ctx.stop()

        stage1.process = stop_after_stage1

        await pipeline.execute(mock_context)

        assert stage2.executed is False  # Skipped (not always_run)
        assert stage3.executed is True   # Executed (always_run)
        assert mock_context.extra["execution_log"] == ["stage1", "stage3"]

    @pytest.mark.asyncio
    async def test_execute_handles_stage_failure(self, mock_context):
        """Should call on_error when stage fails"""
        pipeline = StandardPipeline()
        stage = MockStage(100, "stage1", should_fail=True)
        pipeline.add_stage(stage)

        with pytest.raises(RuntimeError, match="stage1 failed"):
            await pipeline.execute(mock_context)

        assert stage.executed is True

    @pytest.mark.asyncio
    async def test_execute_recovers_from_error(self, mock_context):
        """Should continue after recoverable error"""
        pipeline = StandardPipeline()
        stage1 = RecoverableStage(100, "stage1")
        stage2 = MockStage(200, "stage2")

        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)

        result = await pipeline.execute(mock_context)

        assert stage1.executed is True
        assert stage1.error_handled is True
        assert stage2.executed is True  # Continued after recovery
        assert result.extra["recovered_from"] == "stage1"
        assert result.extra["execution_log"] == ["stage2"]

    @pytest.mark.asyncio
    async def test_execute_stops_on_unrecoverable_error(self, mock_context):
        """Should stop pipeline on unrecoverable error"""
        pipeline = StandardPipeline()
        stage1 = MockStage(100, "stage1", should_fail=True)
        stage2 = MockStage(200, "stage2")

        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)

        with pytest.raises(RuntimeError, match="stage1 failed"):
            await pipeline.execute(mock_context)

        assert stage1.executed is True
        assert stage2.executed is False  # Not executed

    @pytest.mark.asyncio
    async def test_execute_emits_after_event_on_error(self, mock_context, mock_bus):
        """Should emit after event even when stage fails"""
        pipeline = StandardPipeline(bus=mock_bus)
        stage = RecoverableStage(100, "stage1")
        pipeline.add_stage(stage)

        await pipeline.execute(mock_context)

        # Check after event was emitted despite error
        assert any(
            call_args[0][0] == "pipeline_stage_after_stage1"
            for call_args in mock_bus.emit.call_args_list
        )

    @pytest.mark.asyncio
    async def test_execute_without_bus_no_events(self, mock_context):
        """Should not emit events when bus is None"""
        pipeline = StandardPipeline(bus=None)
        stage = MockStage(100, "stage1")
        pipeline.add_stage(stage)

        # Should not raise when bus is None
        result = await pipeline.execute(mock_context)

        assert stage.executed is True

    @pytest.mark.asyncio
    async def test_execute_measures_stage_timing(self, mock_context):
        """Should measure stage execution time (visible in logs)"""
        pipeline = StandardPipeline()
        stage = MockStage(100, "stage1", delay=0.05)
        pipeline.add_stage(stage)

        start = time.perf_counter()
        await pipeline.execute(mock_context)
        elapsed = time.perf_counter() - start

        # Stage with 0.05s delay should take at least that long
        assert elapsed >= 0.05
        assert stage.executed is True

    @pytest.mark.asyncio
    async def test_execute_returns_modified_context(self, mock_context):
        """Should return the context after modifications"""
        pipeline = StandardPipeline()

        class ModifyingStage(PipelineStage):
            async def process(self, ctx):
                ctx.user_text = "Modified"
                ctx.extra["modified"] = True

        stage = ModifyingStage(100, "stage1")
        pipeline.add_stage(stage)

        result = await pipeline.execute(mock_context)

        assert result is mock_context
        assert result.user_text == "Modified"
        assert result.extra["modified"] is True

    @pytest.mark.asyncio
    async def test_execute_event_order(self, mock_context, mock_bus):
        """Events should be emitted in correct order"""
        pipeline = StandardPipeline(bus=mock_bus)
        pipeline.add_stage(MockStage(100, "stage1"))

        await pipeline.execute(mock_context)

        # Get event names in order
        event_names = [call_args[0][0] for call_args in mock_bus.emit.call_args_list]

        # before should come before after
        before_idx = event_names.index("pipeline_stage_before_stage1")
        after_idx = event_names.index("pipeline_stage_after_stage1")
        assert before_idx < after_idx
