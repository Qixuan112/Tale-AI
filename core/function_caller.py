"""
Function Calling 执行器 - 解析和执行工具调用
"""
import json
import re
import time
from functools import wraps
from typing import Callable, Dict
from collections import defaultdict
from threading import Lock

from .tools import browser
from .tools.registry import get_registry, get_tools_list, format_tools_for_chatllm
from .utils.calculator import safe_calculate
from .utils import get_logger

logger = get_logger(__name__)

# Handler registry — unified storage for all tool handlers
_handler_registry: Dict[str, Callable] = {}

# Plugin tool dispatch — populated by PluginManager (deprecated, use _handler_registry)
_plugin_dispatch: Dict[str, Callable] = {}

# 工具使用统计
_tool_stats = {
    "total_calls": 0,
    "success_count": 0,
    "failure_count": 0,
    "by_tool": defaultdict(lambda: {"calls": 0, "success": 0, "failure": 0, "total_time_ms": 0})
}
_stats_lock = Lock()


def get_tool_stats() -> dict:
    """获取工具使用统计"""
    with _stats_lock:
        # 转换 defaultdict 为普通 dict
        return {
            "total_calls": _tool_stats["total_calls"],
            "success_count": _tool_stats["success_count"],
            "failure_count": _tool_stats["failure_count"],
            "by_tool": {k: dict(v) for k, v in _tool_stats["by_tool"].items()}
        }


def _record_tool_stat(func_name: str, success: bool, elapsed_ms: int):
    """记录工具统计"""
    with _stats_lock:
        _tool_stats["total_calls"] += 1
        if success:
            _tool_stats["success_count"] += 1
        else:
            _tool_stats["failure_count"] += 1

        tool_stat = _tool_stats["by_tool"][func_name]
        tool_stat["calls"] += 1
        tool_stat["success" if success else "failure"] += 1
        tool_stat["total_time_ms"] += elapsed_ms


def register_handler(func_name: str, handler: Callable) -> None:
    """
    Register a tool handler.

    This is the unified entry point for registering handlers for both
    built-in and plugin tools. ToolRegistry calls this automatically
    when a tool with a handler is registered.

    Args:
        func_name: Tool name
        handler: Callable that accepts (parameters: dict) -> dict
    """
    _handler_registry[func_name] = handler


def unregister_handler(func_name: str) -> None:
    """Remove a tool handler from the registry."""
    _handler_registry.pop(func_name, None)


def register_plugin_handler(func_name: str, handler: Callable) -> None:
    """Register a plugin-provided tool handler. Called by PluginManager."""
    _plugin_dispatch[func_name] = handler
    # Also register in unified registry
    register_handler(func_name, handler)


def _unregister_plugin_handler(func_name: str) -> None:
    """Remove a plugin-provided tool handler."""
    _plugin_dispatch.pop(func_name, None)
    unregister_handler(func_name)


# 兼容旧代码：从注册表动态生成 AVAILABLE_TOOLS
_registry = get_registry()
AVAILABLE_TOOLS = {t.name: {
    "description": t.description,
    "parameters": {p.name: p.description for p in t.parameters}
} for t in _registry.list_tools()}


def parse_function_call(response_text: str) -> dict:
    """
    从 AI 回复中解析 function call (JSON 格式)
    
    支持的格式：
    ```json
    {
      "function": "browser_search",
      "arguments": {
        "query": "今天黄金价格",
        "engine": "duckduckgo"
      }
    }
    ```
    
    Args:
        response_text: AI 的回复文本
        
    Returns:
        {"name": "函数名", "parameters": {参数字典}} 或 None
    """
    try:
        # 尝试提取 JSON 块
        # 先尝试匹配 ```json ... ``` 格式
        json_pattern = r'```json\s*(.*?)\s*```'
        match = re.search(json_pattern, response_text, re.DOTALL)
        
        if match:
            json_str = match.group(1)
        else:
            # 尝试直接解析整个文本
            json_str = response_text.strip()
        
        # 解析 JSON
        data = json.loads(json_str)
        
        # 检查必需字段（非 dict 结果，如裸数字/null，视为不是 function call）
        if isinstance(data, dict) and "function" in data and "arguments" in data:
            return {
                "name": data["function"],
                "parameters": data["arguments"]
            }

        return None

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def execute_function(func_name: str, parameters: dict) -> dict:
    """
    执行指定的函数

    Args:
        func_name: 函数名
        parameters: 参数字典

    Returns:
        执行结果字典
    """
    start_time = time.time()
    logger.info(f"[Tool] 开始执行: {func_name}", extra={
        "tool_name": func_name,
        "parameters": parameters
    })

    try:
        result = _execute_function_impl(func_name, parameters)
        elapsed = time.time() - start_time
        elapsed_ms = int(elapsed * 1000)

        status = result.get("status", "unknown")
        success = status == "success"
        logger.info(f"[Tool] 完成: {func_name} ({elapsed:.2f}s)", extra={
            "tool_name": func_name,
            "status": status,
            "elapsed_ms": elapsed_ms
        })

        _record_tool_stat(func_name, success, elapsed_ms)
        return result

    except Exception as e:
        elapsed = time.time() - start_time
        elapsed_ms = int(elapsed * 1000)
        logger.error(f"[Tool] 失败: {func_name} ({elapsed:.2f}s)", extra={
            "tool_name": func_name,
            "error": str(e),
            "elapsed_ms": elapsed_ms
        }, exc_info=True)

        _record_tool_stat(func_name, False, elapsed_ms)
        return {"status": "failed", "error": str(e)}


def _execute_function_impl(func_name: str, parameters: dict) -> dict:
    """
    执行指定的函数（内部实现）

    Args:
        func_name: 函数名
        parameters: 参数字典

    Returns:
        执行结果字典
    """
    try:
        # Priority 1: Unified handler registry (new approach)
        if func_name in _handler_registry:
            try:
                return _handler_registry[func_name](parameters)
            except Exception as e:
                logger.error("执行工具 %s 时出错: %s", func_name, e, exc_info=True)
                return {"status": "failed", "error": str(e)}

        # Priority 2: Plugin dispatch (deprecated, migrated to _handler_registry by register_plugin_handler)
        elif func_name in _plugin_dispatch:
            try:
                return _plugin_dispatch[func_name](parameters)
            except Exception as e:
                return {"status": "failed", "error": str(e)}

        else:
            return {"status": "failed", "error": f"未知的函数: {func_name}"}

    except Exception as e:
        logger.error("执行函数 %s 时出错: %s", func_name, e, exc_info=True)
        return {"status": "failed", "error": str(e)}


def handle_function_call(response_text: str) -> tuple:
    """
    处理 function call 的完整流程
    
    Args:
        response_text: AI 的回复文本
        
    Returns:
        (是否有 function call, 执行结果字典或 None)
    """
    func_call = parse_function_call(response_text)
    
    if not func_call:
        return False, None
    
    result = execute_function(func_call["name"], func_call["parameters"])
    return True, result


# 给 ChatLLM 的 Function Calling 提示词模板
# 工具列表从 registry 动态生成，避免与 ToolDefinition 重复维护漂移。
def _render_tools_xml() -> str:
    from xml.sax.saxutils import quoteattr
    blocks = []
    for tool in _registry.list_tools():
        params = "".join(
            f"\n<parameter name={quoteattr(p.name)} description={quoteattr(p.description)}/>"
            for p in tool.parameters
        )
        blocks.append(
            f"<tool name={quoteattr(tool.name)} description={quoteattr(tool.description)}>{params}\n</tool>"
        )
    return "<tools>\n" + "\n\n".join(blocks) + "\n</tools>"


_FUNCTION_CALLING_PROMPT_TEMPLATE = """
你可以使用以下工具来帮助用户：

{tools}

## 使用规则

当用户需要以下操作时，使用对应的工具：
- 打开网页/访问网站 → browser_open
- 搜索信息 → browser_search
- 查询天气 → weather_query
- 数学计算 → calculator
- 拍照/拍一张真实照片 → take_photo
- 画画/绘制插画/创作艺术图 → draw_picture

## 输出格式

需要使用工具时，按以下 XML 格式输出：

<function_calls>
<invoke name="工具名">
<parameter name="参数名">参数值</parameter>
</invoke>
</function_calls>

## 示例

用户："打开百度"
回复：
<function_calls>
<invoke name="browser_open">
<parameter name="url">https://www.baidu.com</parameter>
</invoke>
</function_calls>

用户："搜索今天黄金价格"
回复：
<function_calls>
<invoke name="browser_search">
<parameter name="query">今天黄金价格</parameter>
<parameter name="engine">duckduckgo</parameter>
</invoke>
</function_calls>

用户："北京天气怎么样"
回复：
<function_calls>
<invoke name="weather_query">
<parameter name="city">北京</parameter>
</invoke>
</function_calls>

用户："计算 15 * 23"
回复：
<function_calls>
<invoke name="calculator">
<parameter name="expression">15*23</parameter>
</invoke>
</function_calls>

用户："画一只橘猫趴在窗台上看夕阳"
回复：
<function_calls>
<invoke name="draw_picture">
<parameter name="prompt">一只橘猫趴在窗台上看夕阳，暖色调</parameter>
<parameter name="size">1024x1024</parameter>
<parameter name="style">水彩</parameter>
</invoke>
</function_calls>

## 注意事项
- 一次只能调用一个工具
- 参数值要准确完整
- 如果不需要工具，直接回复用户即可
"""


def get_function_calling_prompt() -> str:
    """构建 ChatLLM 的 Function Calling 提示词（工具列表从 registry 动态注入）。"""
    return _FUNCTION_CALLING_PROMPT_TEMPLATE.format(tools=_render_tools_xml())


# 向后兼容：保留模块级常量供旧引用（在导入时生成一次）
FUNCTION_CALLING_PROMPT = get_function_calling_prompt()
