"""PipelineStage - 管道阶段抽象基类

每个 Stage 负责一个独立职责，可单元测试。
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging


logger = logging.getLogger(__name__)


class PipelineStage(ABC):
    """管道阶段抽象基类

    每个 Stage 实现一个独立职责（元数据构建、LLM 调用、消息发送等），
    按 order 排序执行。
    """

    def __init__(self, order: int, name: str, always_run: bool = False):
        """初始化 Stage

        Args:
            order: 执行顺序（数字越小越早执行）
            name: Stage 名称（用于日志和事件）
            always_run: 是否总是执行（即使前面的 Stage 设置了 stop）
        """
        self.order = order
        self.name = name
        self.always_run = always_run

    @abstractmethod
    async def process(self, ctx) -> None:
        """处理上下文

        Args:
            ctx: PipelineContext 实例

        Raises:
            Exception: 处理失败时抛出异常
        """
        pass

    async def on_error(self, ctx, error: Exception) -> bool:
        """错误处理钩子

        Args:
            ctx: PipelineContext 实例
            error: 捕获的异常

        Returns:
            True 表示已恢复，继续执行后续 Stage
            False 表示无法恢复，终止管道
        """
        logger.error(
            "[%s] Stage 处理失败: %s",
            self.name, error, exc_info=True
        )
        return False  # 默认不恢复，终止管道

    def __repr__(self):
        return f"<{self.__class__.__name__} order={self.order} name={self.name}>"
