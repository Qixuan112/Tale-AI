"""PipelineContext - 管道上下文

贯穿各 Stage 的共享状态，类似 #140 设计的 ReplyContext。
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from core.adapter.message_processor import ProcessedMessage


@dataclass
class PipelineContext:
    """管道执行上下文，贯穿所有 Stage"""

    # ===== 输入（只读） =====
    processed: ProcessedMessage
    adapter_instance: Optional[str] = None

    # ===== 会话信息 =====
    sid: Optional[str] = None
    session_enabled: bool = True
    is_group: bool = False
    target_id: str = ""
    platform_name: str = ""

    # ===== 用户输入构建 =====
    user_text: str = ""  # 格式化后的用户消息：[At xxx] [Reply xxx] 内容
    persist_content: str = ""  # 落库用的纯净原文（不含上下文/VLM 结果）
    user_input: str = ""  # 最终喂给 LLM 的完整 prompt（含元数据/上下文/VLM）

    # ===== 跨会话消息 =====
    inbox_msgs: List[Dict] = field(default_factory=list)
    accessible_sessions: List[str] = field(default_factory=list)

    # ===== LLM 调用 =====
    chatllm_reply: Optional[str] = None
    parsed: Optional[Dict] = None

    # ===== 消息发送 =====
    messages_to_send: List[Any] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)

    # ===== 控制流 =====
    should_stop: bool = False  # Stage 可设置为 True 提前终止管道
    skip_reply: bool = False  # AI 主动选择不回复（<msg></msg>）

    # ===== 扩展字段（插件用） =====
    extra: Dict[str, Any] = field(default_factory=dict)

    def stop(self):
        """设置终止标志，后续 Stage 不再执行"""
        self.should_stop = True
