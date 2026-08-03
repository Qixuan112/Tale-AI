"""MetadataBuilder - 构建消息元数据段落

从 ProcessedMessage 提取结构化元数据，包括：
- 时间信息
- 消息元数据（ID、发送者、群组）
- 环境信息（平台、聊天类型）
- 富媒体信息（语音、表情、视频、文件）
"""

import datetime
from typing import Optional, List
from core.adapter.message_processor import ProcessedMessage
from core.utils.id_sanitizer import IDSanitizer


class MetadataBuilder:
    """构建消息元数据上下文"""

    def __init__(self, id_sanitizer: Optional[IDSanitizer] = None):
        """初始化元数据构建器

        Args:
            id_sanitizer: ID脱敏器，None时创建新实例
        """
        self._id_sanitizer = id_sanitizer or IDSanitizer()

    def build_metadata(
        self,
        processed: ProcessedMessage,
        platform_name: str,
        user_text: str
    ) -> str:
        """构建完整的元数据段落

        Args:
            processed: 处理后的消息
            platform_name: 平台名称
            user_text: 格式化后的用户消息文本

        Returns:
            格式化的元数据字符串
        """
        sections = []

        # 1. 时间信息
        sections.append(self._build_time_section())

        # 2. 消息元数据
        sections.append(self._build_message_metadata(processed))

        # 3. 环境信息
        sections.append(self._build_environment_info(processed, platform_name))

        # 4. 富媒体信息
        media_section = self._build_media_info(processed)
        if media_section:
            sections.append(media_section)

        return "\n\n".join(sections)

    def _build_time_section(self) -> str:
        """构建时间信息段落"""
        now = datetime.datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")
        return f"[当前时间] {time_str}"

    def _build_message_metadata(self, processed: ProcessedMessage) -> str:
        """构建消息元数据段落（ID脱敏）"""
        masked_sender_id = self._id_sanitizer.sanitize_user_id(processed.sender_id)

        lines = ["[消息元数据]"]
        lines.append(f"- 消息ID: {processed.message_id}")
        lines.append(f"- 发送者: {processed.sender_name} ({masked_sender_id})")

        if processed.is_group_message:
            masked_group_id = self._id_sanitizer.sanitize_group_id(processed.group_id)
            if processed.group_name:
                lines.append(f"- 群组: {processed.group_name} ({masked_group_id})")
            else:
                lines.append(f"- 群组ID: {masked_group_id}")

        return "\n".join(lines)

    def _build_environment_info(
        self,
        processed: ProcessedMessage,
        platform_name: str
    ) -> str:
        """构建环境信息段落"""
        chat_type = "群聊" if processed.is_group_message else "私聊"

        lines = ["[环境信息]"]
        lines.append(f"- 平台: {platform_name}")
        lines.append(f"- 类型: {chat_type}")

        return "\n".join(lines)

    def _build_media_info(self, processed: ProcessedMessage) -> str:
        """构建富媒体信息段落"""
        extra_media = []

        if processed.voices:
            extra_media.append(f"- 语音消息: {len(processed.voices)} 条")
        if processed.faces:
            extra_media.append(f"- QQ表情: {len(processed.faces)} 个")
        if processed.stickers:
            extra_media.append(f"- 动画表情: {len(processed.stickers)} 个")
        if processed.videos:
            extra_media.append(f"- 视频: {len(processed.videos)} 个")
        if processed.files:
            file_names = ", ".join(f.name for f in processed.files[:5])
            extra_media.append(f"- 文件: {len(processed.files)} 个 ({file_names})")

        if extra_media:
            return "[附件信息]\n" + "\n".join(extra_media)

        return ""

    def format_user_message(self, processed: ProcessedMessage) -> str:
        """格式化用户消息主体：[At xxx] [Reply xxx] 内容

        Args:
            processed: 处理后的消息

        Returns:
            格式化的用户消息字符串
        """
        msg_parts = []

        # At 标签
        if processed.at_targets:
            for at_id in processed.at_targets:
                msg_parts.append(f"[At {at_id}]")

        # Reply 标签
        if processed.reply_to:
            if processed.reply_text:
                msg_parts.append(f"[回复: {processed.reply_text}]")
            else:
                msg_parts.append(f"[Reply {processed.reply_to}]")

        # 消息内容
        msg_parts.append(processed.text or "")

        return " ".join(msg_parts)
