import re
from typing import Callable, Dict
from xml.etree import ElementTree as ET
from .message import Text, Emoji, At, Act, Message
from .utils import get_logger

logger = get_logger(__name__)

# Plugin tag handler registry — populated by PluginManager
_plugin_tag_handlers: Dict[str, Callable] = {}


def _register_tag_handler(tag_name: str, handler: Callable) -> None:
    """Register a plugin handler for a custom XML tag."""
    _plugin_tag_handlers[tag_name] = handler


def _unregister_tag_handler(tag_name: str) -> None:
    """Remove a plugin tag handler."""
    _plugin_tag_handlers.pop(tag_name, None)


def parse_xml_msg(xml_data):
    """
    解析 AI 返回的 XML 格式消息

    Args:
        xml_data: XML 字符串（非标准格式，可能包含多个根元素）

    Returns:
        dict: {
            "messages": [Message对象列表],
            "action": str或None,  # 第一个动作指令（兼容旧版）
            "actions": [str列表],  # 所有动作指令
            "plan": str或None
        }
    """
    # 清理 XML 数据（移除可能导致解析错误的字符）
    cleaned_data = xml_data.strip()
    if not cleaned_data:
        return {"messages": [], "action": None, "actions": [], "plan": None}

    # 技巧：手动添加 <root> 标签使其成为标准 XML
    try:
        root = ET.fromstring(f"<root>{cleaned_data}</root>")
    except ET.ParseError as e:
        logger.warning("XML 解析失败: %s，尝试降级策略", e)
        # 降级策略1：尝试清理常见非法字符后再解析
        sanitized = _sanitize_xml(cleaned_data)
        try:
            root = ET.fromstring(f"<root>{sanitized}</root>")
        except ET.ParseError:
            # 降级策略2：直接提取文本内容作为回退
            logger.warning("XML 二次解析失败，回退到纯文本提取")
            return _fallback_extract(cleaned_data, str(e))
        return _parse_root(root)

    return _parse_root(root)


def _sanitize_xml(data: str) -> str:
    """清理 XML 中的常见非法字符"""
    # 替换未闭合的 XML 特殊字符
    data = data.replace('&', '&amp;')
    # 恢复已经正确的实体引用
    data = data.replace('&amp;lt;', '&lt;')
    data = data.replace('&amp;gt;', '&gt;')
    data = data.replace('&amp;amp;', '&amp;')
    # 控制字符
    data = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', data)
    return data


def _fallback_extract(data: str, error_msg: str) -> dict:
    """
    XML 解析完全失败时的降级策略：
    尝试用正则提取 <msg><text> 内容，否则将整个文本作为普通消息
    """
    result = {
        "messages": [],
        "action": None,
        "actions": [],
        "plan": None,
        "tool": None,
        "parse_error": error_msg,
    }

    # 尝试正则提取 <msg><text>...</text></msg>
    text_pattern = re.compile(r'<text>\s*(.*?)\s*</text>', re.DOTALL)
    matches = text_pattern.findall(data)

    if matches:
        for text in matches:
            msg = Message()
            msg.add_element(Text(text.strip()))
            result["messages"].append(msg)
    else:
        # 最终回退：将整个内容作为纯文本消息
        msg = Message()
        msg.add_element(Text(data.strip()))
        result["messages"].append(msg)

    # 尝试提取 <act>
    act_pattern = re.compile(r'<act>\s*(.*?)\s*</act>', re.DOTALL)
    for m in act_pattern.findall(data):
        result["actions"].append(m.strip())
    if result["actions"]:
        result["action"] = result["actions"][0]

    # 尝试提取 <plan>
    plan_match = re.search(r'<plan>\s*(.*?)\s*</plan>', data, re.DOTALL)
    if plan_match:
        result["plan"] = plan_match.group(1).strip()

    # 尝试提取 <tool>
    tool_match = re.search(r'<tool>\s*(.*?)\s*</tool>', data, re.DOTALL)
    if tool_match:
        result["tool"] = tool_match.group(1).strip()

    return result


def _parse_root(root: ET.Element) -> dict:
    """从已解析的 XML 根节点提取数据"""
    result = {
        "messages": [],
        "action": None,
        "actions": [],
        "plan": None,
        "tool": None,
    }

    # 解析 <msg> 标签
    for msg_elem in root.findall("msg"):
        message = Message()

        for child in msg_elem:
            tag = child.tag
            value = child.text.strip() if child.text else ""

            if tag == "text":
                message.add_element(Text(value))
            elif tag == "emoji":
                message.add_element(Emoji(value))
            elif tag == "at_targets":
                message.at_targets = [t.strip() for t in value.split(",") if t.strip()]

        if message.elements:
            result["messages"].append(message)

    # 解析 <act> 动作标签 → 发给 ToolLLM（支持多个）
    for act_elem in root.findall("act"):
        action_text = act_elem.text.strip() if act_elem.text else ""
        action_text = action_text.replace("<!--", "").replace("-->", "").strip()
        if action_text:
            result["actions"].append(action_text)

    if result["actions"]:
        result["action"] = result["actions"][0]

    # 解析 <plan> 计划标签 → 发给 PlanLLM
    plan_elem = root.find("plan")
    if plan_elem is not None:
        plan_text = plan_elem.text.strip() if plan_elem.text else ""
        result["plan"] = plan_text.replace("<!--", "").replace("-->", "").strip()

    # 解析 <tool> 工具查询标签 → 查询可用工具列表
    tool_elem = root.find("tool")
    if tool_elem is not None:
        tool_text = tool_elem.text.strip() if tool_elem.text else ""
        result["tool"] = tool_text.replace("<!--", "").replace("-->", "").strip()

    # 处理插件注册的自定义标签
    for tag_name, handler in _plugin_tag_handlers.items():
        for elem in root.findall(tag_name):
            try:
                key = f"plugin_{tag_name}"
                value = handler(tag_name, elem, {"parse_for": "chatllm"})
                if key not in result:
                    result[key] = []
                result[key].append(value)
            except Exception as e:
                logger.warning("Plugin tag handler '%s' failed: %s", tag_name, e)

    return result


def format_message_for_display(message):
    """
    将 Message 对象格式化为可显示的字符串
    """
    parts = []
    for elem in message.elements:
        if isinstance(elem, Text):
            parts.append(elem.content)
        elif isinstance(elem, Emoji):
            parts.append(elem.content)

    text = "".join(parts)

    if message.at_targets:
        at_str = " @".join(message.at_targets)
        text = f"@{at_str} {text}"

    return text
