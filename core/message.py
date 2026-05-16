"""消息类型定义"""


class MessageElement:
    """消息元素基类"""
    def __init__(self, content):
        self.content = content

    def __repr__(self):
        return f"{self.__class__.__name__}({self.content!r})"


class Text(MessageElement):
    """文本消息"""
    pass


class Emoji(MessageElement):
    """表情消息"""
    pass


class At(MessageElement):
    """@某人消息"""
    pass


class Act(MessageElement):
    """动作/指令消息"""
    pass


class Message:
    """完整消息，包含多个元素"""
    def __init__(self, elements=None, at_targets=None):
        self.elements = elements or []
        self.at_targets = at_targets or []

    def add_element(self, element):
        self.elements.append(element)

    def __repr__(self):
        return f"Message(elements={self.elements}, at_targets={self.at_targets})"
