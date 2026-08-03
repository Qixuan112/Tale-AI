"""
ID脱敏器

用于将敏感的用户ID/群ID打码，防止AI在回复中泄露真实QQ号等敏感信息。
维护真实ID与打码ID的双向映射。
"""


class IDSanitizer:
    """ID脱敏器，维护真实ID与打码ID的映射"""

    def __init__(self):
        self._user_map = {}  # usr_xxx -> real_id
        self._group_map = {}  # grp_xxx -> real_id
        self._reverse_user = {}  # real_id -> usr_xxx
        self._reverse_group = {}  # real_id -> grp_xxx
        self._counter = 1000
        self._max_counter = 9999  # 最大值，达到后循环复用

    def sanitize_user_id(self, real_id: str) -> str:
        """
        用户ID打码：123456 -> ****3456

        Args:
            real_id: 真实用户ID

        Returns:
            打码后的ID（****xxxx格式）
        """
        if not real_id:
            return ""

        real_id = str(real_id)  # 确保是字符串

        if real_id in self._reverse_user:
            return self._reverse_user[real_id]

        # 使用****前缀 + 最后4位（不足4位则补充序号）
        if len(real_id) >= 4:
            suffix = real_id[-4:]
        else:
            suffix = f"{real_id}{self._counter}"[-4:]

        masked = f"****{suffix}"
        self._counter += 1
        if self._counter > self._max_counter:
            self._counter = 1000  # 循环复用，避免无限增长
        self._user_map[masked] = real_id
        self._reverse_user[real_id] = masked
        return masked

    def sanitize_group_id(self, real_id: str) -> str:
        """
        群ID打码：987654 -> ****7654

        Args:
            real_id: 真实群ID

        Returns:
            打码后的ID（****xxxx格式）
        """
        if not real_id:
            return ""

        real_id = str(real_id)  # 确保是字符串

        if real_id in self._reverse_group:
            return self._reverse_group[real_id]

        # 使用****前缀 + 最后4位（不足4位则补充序号）
        if len(real_id) >= 4:
            suffix = real_id[-4:]
        else:
            suffix = f"{real_id}{self._counter}"[-4:]

        masked = f"****{suffix}"
        self._counter += 1
        if self._counter > self._max_counter:
            self._counter = 1000  # 循环复用，避免无限增长
        self._group_map[masked] = real_id
        self._reverse_group[real_id] = masked
        return masked

    def restore_user_id(self, masked: str) -> str:
        """
        还原用户ID：****3456 -> 123456

        Args:
            masked: 打码ID

        Returns:
            真实ID，如果不是打码ID则原样返回
        """
        if not masked:
            return ""
        return self._user_map.get(masked, masked)

    def restore_group_id(self, masked: str) -> str:
        """
        还原群ID：****7654 -> 987654

        Args:
            masked: 打码ID

        Returns:
            真实ID，如果不是打码ID则原样返回
        """
        if not masked:
            return ""
        return self._group_map.get(masked, masked)

    def is_masked_user_id(self, id_str: str) -> bool:
        """判断是否为打码的用户ID"""
        return bool(id_str and id_str.startswith("****"))

    def is_masked_group_id(self, id_str: str) -> bool:
        """判断是否为打码的群ID"""
        return bool(id_str and id_str.startswith("****"))
