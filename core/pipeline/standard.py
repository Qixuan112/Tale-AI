"""StandardPipeline - 标准消息处理管道

顺序执行所有 Stage，支持插件 hook、错误恢复和提前终止。
"""

import logging
import time
from typing import Optional

from .base import MessagePipeline
from .context import PipelineContext
from .stage import PipelineStage


logger = logging.getLogger(__name__)


class StandardPipeline(MessagePipeline):
    """标准管道：顺序执行 Stage，支持插件 hook 和错误恢复"""

    def __init__(self, bus=None):
        """初始化标准管道

        Args:
            bus: EventBus 实例，用于发送插件 hook 事件（可选）
        """
        super().__init__()
        self._bus = bus

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """执行管道

        按 order 顺序执行所有 Stage，每个 Stage 前后发送事件供插件 hook。

        Args:
            ctx: 管道上下文

        Returns:
            处理后的上下文
        """
        for stage in self._stages:
            # 检查终止标志（always_run 的 Stage 无视终止标志）
            if ctx.should_stop and not stage.always_run:
                logger.debug("[%s] 跳过（管道已终止）", stage.name)
                continue

            # before hook
            if self._bus:
                self._bus.emit(f"pipeline_stage_before_{stage.name}", ctx)

            start_time = time.perf_counter()

            try:
                logger.debug("[%s] 开始执行", stage.name)
                await stage.process(ctx)
                elapsed = (time.perf_counter() - start_time) * 1000
                logger.debug("[%s] 完成 (%.1fms)", stage.name, elapsed)

            except Exception as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                logger.error(
                    "[%s] 失败 (%.1fms): %s",
                    stage.name, elapsed, e, exc_info=True
                )

                # 调用 Stage 的错误处理钩子
                recovered = await stage.on_error(ctx, e)
                if not recovered:
                    # 无法恢复，终止管道
                    logger.error("[%s] 无法恢复，终止管道", stage.name)
                    raise

                logger.info("[%s] 已恢复，继续执行", stage.name)

            # after hook
            if self._bus:
                self._bus.emit(f"pipeline_stage_after_{stage.name}", ctx)

        return ctx
