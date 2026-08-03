"""MessagePipeline - 消息处理管道抽象基类

定义管道的执行接口和插件 hook 点。
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import logging

from .stage import PipelineStage
from .context import PipelineContext


logger = logging.getLogger(__name__)


class MessagePipeline(ABC):
    """消息处理管道抽象基类

    管理 Stage 的注册、排序和执行，支持插件 hook。
    """

    def __init__(self):
        self._stages: List[PipelineStage] = []

    def add_stage(self, stage: PipelineStage):
        """注册一个 Stage

        Args:
            stage: PipelineStage 实例
        """
        self._stages.append(stage)
        # 按 order 排序
        self._stages.sort(key=lambda s: s.order)

    def get_stages(self) -> List[PipelineStage]:
        """获取所有 Stage（按 order 排序）

        Returns:
            Stage 列表
        """
        return self._stages.copy()

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """执行管道

        Args:
            ctx: 管道上下文

        Returns:
            处理后的上下文

        Raises:
            Exception: 管道执行失败
        """
        pass
