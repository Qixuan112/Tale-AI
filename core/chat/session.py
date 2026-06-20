"""会话数据模型"""

from dataclasses import dataclass


@dataclass
class Session:
    """会话标识与元数据

    sid 格式: {adapter_name}:{session_type}:{session_id}
    示例: "qq:gm:720878872" 表示 QQ 群聊 720878872
          "qq:dm:3573568193" 表示 QQ 私聊 3573568193

    所有地方统一使用 Session.sid 属性，禁止手动拼接字符串。
    """

    adapter_name: str = ""
    """平台适配器名，如 "qq"、"wechat" """

    session_type: str = ""
    """会话类型 "gm"(group message, 群聊) 或 "dm"(direct message, 私聊)"""

    session_id: str = ""
    """群号或用户 ID"""

    session_title: str = ""
    """会话标题，群名或用户昵称"""

    session_description: str = ""
    """会话描述，可供 AI 理解会话上下文"""

    timestamp: int = 0
    """最后活跃时间戳"""

    enabled: bool = True
    """是否启用。禁用的会话不加载其历史作为 AI 上下文"""

    @property
    def sid(self) -> str:
        return f"{self.adapter_name}:{self.session_type}:{self.session_id}"

    @classmethod
    def from_sid(cls, sid: str) -> "Session":
        """从 sid 字符串解析 Session 对象"""
        parts = sid.split(":", maxsplit=2)
        if len(parts) != 3:
            raise ValueError(f"Invalid sid format: {sid!r}, expected adapter:type:id")
        return cls(adapter_name=parts[0], session_type=parts[1], session_id=parts[2])

    def __str__(self) -> str:
        return self.sid
