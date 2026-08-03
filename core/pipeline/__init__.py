"""Pipeline 消息处理管道

将 _handle_respond_message 的职责拆分为独立的 Stage，
支持插件 hook、错误恢复和可测试性。
"""

from .context import PipelineContext
from .stage import PipelineStage
from .base import MessagePipeline
from .standard import StandardPipeline

__all__ = [
    "PipelineContext",
    "PipelineStage",
    "MessagePipeline",
    "StandardPipeline",
]
