"""
Unit tests for PipelineStage

Tests the abstract base class for all pipeline stages.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext


class MockStage(PipelineStage):
    """Concrete implementation for testing"""

    def __init__(self, order=100, name="mock_stage", always_run=False):
        super().__init__(order, name, always_run)
        self.process_called = False
        self.process_exception = None

    async def process(self, ctx):
        """Mock process implementation"""
        self.process_called = True
        if self.process_exception:
            raise self.process_exception
        # Modify context to prove it was called
        ctx.extra["mock_stage_executed"] = True


class MockRecoverableStage(PipelineStage):
    """Stage that can recover from errors"""

    def __init__(self):
        super().__init__(order=200, name="recoverable_stage")
        self.recovery_called = False

    async def process(self, ctx):
        raise ValueError("Intentional error")

    async def on_error(self, ctx, error):
        """Override to recover from errors"""
        self.recovery_called = True
        ctx.extra["recovered"] = True
        return True  # Signal recovery


class TestPipelineStage:
    """Test PipelineStage abstract base class"""

    def test_stage_initialization(self):
        """Should initialize with required parameters"""
        stage = MockStage(order=100, name="test_stage", always_run=False)

        assert stage.order == 100
        assert stage.name == "test_stage"
        assert stage.always_run is False

    def test_stage_always_run_flag(self):
        """always_run flag should be configurable"""
        stage1 = MockStage(order=100, name="stage1", always_run=False)
        stage2 = MockStage(order=200, name="stage2", always_run=True)

        assert stage1.always_run is False
        assert stage2.always_run is True

    @pytest.mark.asyncio
    async def test_process_is_abstract(self):
        """process() must be implemented by subclasses"""
        # PipelineStage itself cannot be instantiated
        with pytest.raises(TypeError):
            PipelineStage(100, "test")

    @pytest.mark.asyncio
    async def test_process_can_modify_context(self):
        """process() should be able to modify context"""
        stage = MockStage()
        ctx = PipelineContext(processed=MagicMock())

        await stage.process(ctx)

        assert stage.process_called is True
        assert ctx.extra.get("mock_stage_executed") is True

    @pytest.mark.asyncio
    async def test_on_error_default_returns_false(self):
        """Default on_error() should return False (no recovery)"""
        stage = MockStage()
        stage.process_exception = ValueError("Test error")
        ctx = PipelineContext(processed=MagicMock())

        error = ValueError("Test error")
        recovered = await stage.on_error(ctx, error)

        assert recovered is False

    @pytest.mark.asyncio
    async def test_on_error_can_be_overridden(self):
        """on_error() can be overridden for custom recovery"""
        stage = MockRecoverableStage()
        ctx = PipelineContext(processed=MagicMock())

        error = ValueError("Test error")
        recovered = await stage.on_error(ctx, error)

        assert recovered is True
        assert stage.recovery_called is True
        assert ctx.extra.get("recovered") is True

    @pytest.mark.asyncio
    async def test_on_error_receives_correct_parameters(self):
        """on_error() should receive context and exception"""
        stage = MockStage()
        ctx = PipelineContext(processed=MagicMock())
        test_error = RuntimeError("Custom error")

        # Mock the on_error to capture parameters
        captured = {}

        async def capture_params(context, error):
            captured["context"] = context
            captured["error"] = error
            return False

        stage.on_error = capture_params

        await stage.on_error(ctx, test_error)

        assert captured["context"] is ctx
        assert captured["error"] is test_error

    def test_stage_repr(self):
        """__repr__ should show stage info"""
        stage = MockStage(order=300, name="test_stage")

        repr_str = repr(stage)

        assert "MockStage" in repr_str
        assert "order=300" in repr_str
        assert "name=test_stage" in repr_str

    def test_stages_can_be_compared_by_order(self):
        """Stages should be sortable by order"""
        stage1 = MockStage(order=300, name="stage1")
        stage2 = MockStage(order=100, name="stage2")
        stage3 = MockStage(order=200, name="stage3")

        stages = [stage1, stage2, stage3]
        sorted_stages = sorted(stages, key=lambda s: s.order)

        assert sorted_stages[0].name == "stage2"  # order 100
        assert sorted_stages[1].name == "stage3"  # order 200
        assert sorted_stages[2].name == "stage1"  # order 300

    @pytest.mark.asyncio
    async def test_stage_can_set_stop_flag(self):
        """Stage can set should_stop to terminate pipeline"""
        class StoppingStage(PipelineStage):
            async def process(self, ctx):
                ctx.stop()

        stage = StoppingStage(order=100, name="stopping")
        ctx = PipelineContext(processed=MagicMock())

        assert ctx.should_stop is False
        await stage.process(ctx)
        assert ctx.should_stop is True
