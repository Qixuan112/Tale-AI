"""
工具注册中心

统一管理所有可用工具的定义和元数据，消除多处重复定义。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Callable, Any, Optional


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: List[ToolParameter]
    handler: Optional[Callable] = None  # 执行函数（可选，在 function_caller 中注册）

    def to_dict(self) -> dict:
        """转换为字典（用于 JSON 序列化）"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                p.name: p.description for p in self.parameters
            },
        }

    def to_prompt_format(self, index: int) -> str:
        """生成提示词格式的工具描述"""
        lines = [f"{index}. **{self.name}** - {self.description}"]
        lines.append("   - 参数:")
        for p in self.parameters:
            req_mark = " (必填)" if p.required else " (可选)"
            lines.append(f"     - {p.name}: {p.description}{req_mark}")
        lines.append("")
        return "\n".join(lines)


class ToolRegistry:
    """工具注册表（单例）"""

    _instance: Optional["ToolRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, ToolDefinition] = {}
            cls._instance._register_defaults()
        return cls._instance

    def _register_defaults(self):
        """注册默认工具"""
        self.register(
            ToolDefinition(
                name="browser_open",
                description="打开指定网页",
                parameters=[
                    ToolParameter("url", "网页地址，如 https://www.baidu.com"),
                ],
            )
        )
        self.register(
            ToolDefinition(
                name="browser_search",
                description="使用搜索引擎搜索",
                parameters=[
                    ToolParameter("query", "搜索关键词"),
                    ToolParameter("engine", "搜索引擎：默认 duckduckgo", required=False, default="duckduckgo"),
                ],
            )
        )
        self.register(
            ToolDefinition(
                name="weather_query",
                description="查询城市天气",
                parameters=[
                    ToolParameter("city", "城市名称，如 北京、上海"),
                ],
            )
        )
        self.register(
            ToolDefinition(
                name="calculator",
                description="执行数学计算",
                parameters=[
                    ToolParameter("expression", "数学表达式，如 1+2*3"),
                ],
            )
        )
        self.register(
            ToolDefinition(
                name="query_group_members",
                description="获取群成员列表，查询群里用户的昵称和 QQ 号",
                parameters=[
                    ToolParameter("group_id", "群 ID，如 12345678"),
                ],
            )
        )
        self.register(
            ToolDefinition(
                name="take_photo",
                description="拍照/摄影——拍一张真实感的照片，所见即所得",
                parameters=[
                    ToolParameter("prompt", "想拍的内容，越具体越好，如：一只橘猫趴在窗台上"),
                    ToolParameter("size", "图片尺寸，默认 1024x1024", required=False, default="1024x1024"),
                ],
            )
        )
        self.register(
            ToolDefinition(
                name="draw_picture",
                description="画画/创作——画一张插画或艺术作品，富有创意与风格",
                parameters=[
                    ToolParameter("prompt", "想画的内容，越具体越好，如：一只橘猫趴在窗台上"),
                    ToolParameter("size", "图片尺寸，默认 1024x1024", required=False, default="1024x1024"),
                    ToolParameter("style", "画风偏好（水彩/日系/厚涂/水墨/赛璐珞等），可选", required=False, default=""),
                ],
            )
        )

    def register(self, tool: ToolDefinition) -> None:
        """注册一个工具"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """移除一个工具的定义（插件卸载时调用）"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        """获取所有工具列表"""
        return list(self._tools.values())

    def get_tools_list_text(self) -> str:
        """获取格式化的工具列表文本（用于提示词）"""
        lines = ["## 可用工具列表\n"]
        for i, tool in enumerate(self._tools.values(), 1):
            lines.append(tool.to_prompt_format(i))
        return "\n".join(lines)

    def format_for_chatllm(self) -> str:
        """用 <chatllm> 标签格式化工具列表"""
        tools_text = self.get_tools_list_text()
        return f"<chatllm>\n{tools_text}\n</chatllm>"

    def build_fc_prompt(self) -> str:
        """构建 ToolLLM 的 Function Calling 提示词"""
        tools_text = self.get_tools_list_text()
        return f"""
你是 "ToolLLM"，工具调用专家。你的任务是分析用户的动作指令，输出标准化的 Function Calling JSON。

{tools_text}

## 输出格式

你必须按以下 JSON 格式输出，不要包含任何其他内容：

```json
{{
  "function": "工具名",
  "arguments": {{
    "参数名": "参数值"
  }}
}}
```

## 规则

1. 分析用户的动作指令，选择最合适的工具
2. 提取关键参数值
3. 只输出 JSON，不要有其他文字
4. 一次只能调用一个工具

## 示例

用户动作："打开百度"
输出：
```json
{{
  "function": "browser_open",
  "arguments": {{
    "url": "https://www.baidu.com"
  }}
}}
```

用户动作："搜索今天黄金价格"
输出：
```json
{{
  "function": "browser_search",
  "arguments": {{
    "query": "今天黄金价格",
    "engine": "duckduckgo"
  }}
}}
```

用户动作："查询北京天气"
输出：
```json
{{
  "function": "weather_query",
  "arguments": {{
    "city": "北京"
  }}
}}
```

用户动作："计算 15 * 23 + 8"
输出：
```json
{{
  "function": "calculator",
  "arguments": {{
    "expression": "15*23+8"
  }}
}}
```
"""


# 便捷函数：获取全局注册表实例
_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """获取全局工具注册表实例"""
    return _registry


def get_tools_list() -> str:
    """获取格式化的工具列表"""
    return _registry.get_tools_list_text()


def format_tools_for_chatllm() -> str:
    """用 <chatllm> 标签格式化工具列表"""
    return _registry.format_for_chatllm()


def get_tool(name: str) -> Optional[ToolDefinition]:
    """获取指定工具"""
    return _registry.get(name)


def build_fc_prompt() -> str:
    """构建 Function Calling 提示词"""
    return _registry.build_fc_prompt()
