"""
Unit tests for MessagePipeline base class

Tests pipeline stage registration and ordering.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.pipeline.base import MessagePipeline
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext


class MockPipeline(MessagePipeline):
    """Concrete implementation for testing"""

    async def execute(self, ctx):
        """Mock execute - just call all stages in order"""
        for stage in self._stages:
            await stage.process(ctx)
        return ctx


class MockStage(PipelineStage):
    """Mock stage for testing"""

    def __init__(self, order, name):
        super().__init__(order, name)
        self.executed = False

    async def process(self, ctx):
        self.executed = True
        ctx.extra.setdefault("execution_order", []).append(self.name)


class TestMessagePipeline:
    """Test MessagePipeline base class"""

    def test_pipeline_initialization(self):
        """Should initialize with empty stage list"""
        pipeline = MockPipeline()

        assert pipeline._stages == []
        assert pipeline.get_stages() == []

    def test_add_stage(self):
        """Should add stages to pipeline"""
        pipeline = MockPipeline()
        stage1 = MockStage(100, "stage1")
        stage2 = MockStage(200, "stage2")

        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)

        stages = pipeline.get_stages()
        assert len(stages) == 2

    def test_stages_sorted_by_order(self):
        """Stages should be sorted by order after adding"""
        pipeline = MockPipeline()
        stage1 = MockStage(300, "stage1")
        stage2 = MockStage(100, "stage2")
        stage3 = MockStage(200, "stage3")

        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)
        pipeline.add_stage(stage3)

        stages = pipeline.get_stages()
        assert stages[0].name == "stage2"  # order 100
        assert stages[1].name == "stage3"  # order 200
        assert stages[2].name == "stage1"  # order 300

    def test_add_stage_maintains_sort_order(self):
        """Adding stages in any order should maintain sorted list"""
        pipeline = MockPipeline()

        # Add in reverse order
        pipeline.add_stage(MockStage(500, "stage5"))
        pipeline.add_stage(MockStage(100, "stage1"))
        pipeline.add_stage(MockStage(300, "stage3"))
        pipeline.add_stage(MockStage(200, "stage2"))
        pipeline.add_stage(MockStage(400, "stage4"))

        stages = pipeline.get_stages()
        orders = [s.order for s in stages]
        assert orders == [100, 200, 300, 400, 500]

    def test_get_stages_returns_copy(self):
        """get_stages() should return a copy, not the original list"""
        pipeline = MockPipeline()
        stage = MockStage(100, "stage1")
        pipeline.add_stage(stage)

        stages1 = pipeline.get_stages()
        stages2 = pipeline.get_stages()

        assert stages1 == stages2
        assert stages1 is not stages2  # Different list objects

    def test_modifying_returned_stages_does_not_affect_pipeline(self):
        """Modifying returned stage list should not affect pipeline"""
        pipeline = MockPipeline()
        pipeline.add_stage(MockStage(100, "stage1"))

        stages = pipeline.get_stages()
        stages.append(MockStage(200, "stage2"))

        # Original pipeline should still have only 1 stage
        assert len(pipeline.get_stages()) == 1

    @pytest.mark.asyncio
    async def test_execute_is_abstract(self):
        """execute() must be implemented by subclasses"""
        # MessagePipeline itself cannot be instantiated directly
        with pytest.raises(TypeError):
            MessagePipeline().execute(MagicMock())

    @pytest.mark.asyncio
    async def test_pipeline_executes_stages_in_order(self):
        """Pipeline should execute stages in order"""
        pipeline = MockPipeline()

        # Add stages out of order
        stage3 = MockStage(300, "stage3")
        stage1 = MockStage(100, "stage1")
        stage2 = MockStage(200, "stage2")

        pipeline.add_stage(stage3)
        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)

        ctx = PipelineContext(processed=MagicMock())
        await pipeline.execute(ctx)

        # Check execution order
        assert ctx.extra["execution_order"] == ["stage1", "stage2", "stage3"]
        assert stage1.executed is True
        assert stage2.executed is True
        assert stage3.executed is True

    def test_same_order_stages_maintain_insertion_order(self):
        """Stages with same order should maintain insertion order"""
        pipeline = MockPipeline()

        stage1 = MockStage(100, "stage1")
        stage2 = MockStage(100, "stage2")
        stage3 = MockStage(100, "stage3")

        pipeline.add_stage(stage1)
        pipeline.add_stage(stage2)
        pipeline.add_stage(stage3)

        stages = pipeline.get_stages()
        names = [s.name for s in stages]
        assert names == ["stage1", "stage2", "stage3"]

    def test_multiple_pipelines_are_independent(self):
        """Multiple pipeline instances should not share stages"""
        pipeline1 = MockPipeline()
        pipeline2 = MockPipeline()

        pipeline1.add_stage(MockStage(100, "stage1"))
        pipeline2.add_stage(MockStage(200, "stage2"))

        assert len(pipeline1.get_stages()) == 1
        assert len(pipeline2.get_stages()) == 1
        assert pipeline1.get_stages()[0].name == "stage1"
        assert pipeline2.get_stages()[0].name == "stage2"
