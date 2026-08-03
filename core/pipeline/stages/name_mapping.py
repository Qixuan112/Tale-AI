"""NameMappingStage - 昵称到ID映射

Order: 200
职责：维护昵称→ID 映射表（按群分组），供发送时解析 @ 用
"""

import logging
from typing import Optional, Dict
from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext
from core.utils.cache import BoundedCache

logger = logging.getLogger(__name__)


class NameMappingStage(PipelineStage):
    """昵称映射 Stage

    维护 _name_to_id 映射表（sender_name → masked_id），
    AI 回复时可通过昵称 @ 用户。
    """

    def __init__(self, name_to_id_cache: BoundedCache, id_sanitizer):
        """初始化

        Args:
            name_to_id_cache: 昵称→ID 映射缓存
            id_sanitizer: ID 脱敏器
        """
        super().__init__(order=200, name="name_mapping")
        self._name_to_id = name_to_id_cache
        self._id_sanitizer = id_sanitizer

    async def process(self, ctx: PipelineContext) -> None:
        """更新昵称映射"""
        processed = ctx.processed

        if not processed.sender_name or not processed.sender_id:
            return

        group_key = processed.group_id or "_private"

        # 写时复制模式：每次修改都触发 __setitem__，更新 TTL 和 LRU
        name_map = self._name_to_id.get(group_key, {})
        masked_sender_id = self._id_sanitizer.sanitize_user_id(
            processed.sender_id
        )
        name_map[processed.sender_name] = masked_sender_id
        self._name_to_id[group_key] = name_map  # 触发 __setitem__

        logger.debug(
            "昵称映射: %s → %s (group_key=%s)",
            processed.sender_name,
            masked_sender_id,
            group_key
        )
