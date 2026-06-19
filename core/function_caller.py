"""
Function Calling 执行器 - 解析和执行工具调用
"""
import json
import re
from typing import Callable, Dict

from .tools import browser
from .tools.registry import get_registry, get_tools_list, format_tools_for_chatllm
from .utils.calculator import safe_calculate
from .utils import get_logger

logger = get_logger(__name__)

# Plugin tool dispatch — populated by PluginManager
_plugin_dispatch: Dict[str, Callable] = {}


def register_plugin_handler(func_name: str, handler: Callable) -> None:
    """Register a plugin-provided tool handler. Called by PluginManager."""
    _plugin_dispatch[func_name] = handler


def _unregister_plugin_handler(func_name: str) -> None:
    """Remove a plugin-provided tool handler."""
    _plugin_dispatch.pop(func_name, None)


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
        
        # 检查必需字段
        if "function" in data and "arguments" in data:
            return {
                "name": data["function"],
                "parameters": data["arguments"]
            }
        
        return None
        
    except (json.JSONDecodeError, KeyError):
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
    try:
        if func_name == "browser_open":
            url = parameters.get("url", "")
            if url:
                result = browser.fetch_and_parse(url)
                return result
            return {"status": "failed", "error": "缺少 url 参数"}

        elif func_name == "browser_search":
            query = parameters.get("query", "")
            engine = parameters.get("engine", "duckduckgo")
            if query:
                return browser.browser_search(query, engine)
            return {"status": "failed", "error": "缺少 query 参数"}
        
        elif func_name == "weather_query":
            from .tools import weather
            city = parameters.get("city", "")
            if city:
                return weather.query(city)
            return {"status": "failed", "error": "缺少 city 参数"}
        
        elif func_name == "calculator":
            expression = parameters.get("expression", "")
            if expression:
                return safe_calculate(expression)
            return {"status": "failed", "error": "缺少 expression 参数"}

        elif func_name == "generate_image":
            from .llm.image_gen import get_image_generator
            prompt = parameters.get("prompt", "")
            size = parameters.get("size", "1024x1024") or "1024x1024"
            if not prompt:
                return {"status": "failed", "error": "缺少 prompt 参数"}
            image_url = get_image_generator().generate(prompt, size)
            if image_url:
                return {
                    "status": "success",
                    "image_url": image_url,
                    "message": f"已生成图片，URL: {image_url}。请在回复中用 <image>{image_url}</image> 把这张图发给用户。",
                }
            return {"status": "failed", "error": "图片生成失败（可能未配置 image_gen provider）"}

        elif func_name == "take_photo":
            from .llm.image_gen import get_image_generator
            raw = parameters.get("prompt", "")
            size = parameters.get("size", "1024x1024") or "1024x1024"
            if not raw:
                return {"status": "failed", "error": "缺少 prompt 参数"}
            enriched = f"写实摄影风格，超清照片质感，电影级光影与细节，颜色真实自然，4K画质，景深效果，{raw}"
            image_url = get_image_generator().generate(enriched, size)
            if image_url:
                return {
                    "status": "success",
                    "image_url": image_url,
                    "message": f"已拍照成功，URL: {image_url}。请在回复中用 <image>{image_url}</image> 把这张照片发给用户。",
                }
            return {"status": "failed", "error": "拍照失败（可能未配置 image_gen provider）"}

        elif func_name == "draw_picture":
            from .llm.image_gen import get_image_generator
            raw = parameters.get("prompt", "")
            size = parameters.get("size", "1024x1024") or "1024x1024"
            style = parameters.get("style", "") or ""
            if not raw:
                return {"status": "failed", "error": "缺少 prompt 参数"}
            style_tag = f"{style}风格，" if style else ""
            enriched = f"插画创作，{style_tag}富有艺术感与表现力，色彩丰富协调，画面生动有故事性，{raw}"
            image_url = get_image_generator().generate(enriched, size)
            if image_url:
                return {
                    "status": "success",
                    "image_url": image_url,
                    "message": f"已画好，URL: {image_url}。请在回复中用 <image>{image_url}</image> 把这张画发给用户。",
                }
            return {"status": "failed", "error": "画画失败（可能未配置 image_gen provider）"}
        
        # Plugin dispatch
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
