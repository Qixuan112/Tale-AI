# 插件开发指南

## 概述

Tale-AI 提供了强大的插件系统，允许开发者通过 6 个扩展点来扩展系统功能，无需修改核心代码。插件采用声明式配置 + Python 类实现的方式，支持热加载和运行时启用/禁用。

## 插件结构

一个标准的 Tale-AI 插件包含以下文件：

```
plugins/
└── my_plugin/
    ├── manifest.json    # 插件元数据（必需）
    ├── plugin.py        # 插件实现（必需）
    ├── schema.json      # 配置项定义（可选）
    └── __init__.py      # Python 包标识（可选）
```

### manifest.json

插件元数据文件，定义插件的基本信息和扩展点。

```json
{
  "id": "my_plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "插件功能描述",
  "class": "MyPlugin",
  "hooks": ["tool", "event"],
  "min_tale_version": "1.0.0",
  "builtin": false,
  "requirements": ["requests>=2.28.0"],
  "dependencies": {}
}
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | `string` | 是 | 插件唯一标识符（kebab-case） |
| `name` | `string` | 是 | 插件显示名称 |
| `version` | `string` | 是 | 语义化版本号 |
| `author` | `string` | 否 | 作者名称 |
| `description` | `string` | 否 | 功能描述（支持多行） |
| `class` | `string` | 否 | 插件类名（未指定则自动查找 PluginBase 子类） |
| `hooks` | `array` | 否 | 实现的扩展点（见下文） |
| `min_tale_version` | `string` | 否 | 最低兼容版本（默认 1.0.0） |
| `builtin` | `boolean` | 否 | 是否为内置插件（默认 false） |
| `requirements` | `array` | 否 | Python 依赖包列表 |
| `dependencies` | `object` | 否 | 依赖的其他插件（`{"plugin_id": ">=1.0.0"}`） |

### schema.json

定义插件的配置项和 WebUI 渲染方式（可选）。

```json
[
  {
    "name": "api_key",
    "type": "text",
    "label": "API Key",
    "default": "",
    "required": true,
    "placeholder": "请输入 API Key"
  },
  {
    "name": "enable_cache",
    "type": "checkbox",
    "label": "启用缓存",
    "default": true
  },
  {
    "name": "log_level",
    "type": "select",
    "label": "日志级别",
    "default": "INFO",
    "options": ["DEBUG", "INFO", "WARNING", "ERROR"]
  }
]
```

**支持的字段类型**：
- `text` — 单行文本输入
- `checkbox` — 布尔选择框
- `select` — 下拉选择框
- `number` — 数字输入

## 六大扩展点

### 1. ToolProvider — 自定义工具

提供 AI 可调用的工具函数。

**协议接口**：

```python
from typing import List, Dict, Any
from core.tools.registry import ToolDefinition

class ToolProvider(Protocol):
    def get_tool_definitions(self) -> List[ToolDefinition]: ...
    def execute_tool(self, func_name: str, parameters: dict) -> Any: ...
```

**完整示例**：

```python
from core.plugin.base import PluginBase, ToolProvider
from core.tools.registry import ToolDefinition

class WeatherPlugin(PluginBase, ToolProvider):
    def _activate(self) -> None:
        self.api_key = self.get_config("api_key", "")
        print(f"[WeatherPlugin] 已激活，API Key: {self.api_key[:8]}...")
    
    def _deactivate(self) -> None:
        print("[WeatherPlugin] 已停用")
    
    def get_tool_definitions(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_weather",
                description="查询指定城市的天气信息",
                parameters={
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称，如：北京、上海"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "温度单位",
                            "default": "celsius"
                        }
                    },
                    "required": ["city"]
                }
            )
        ]
    
    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        if func_name == "get_weather":
            city = parameters.get("city", "")
            unit = parameters.get("unit", "celsius")
            # 调用天气 API
            weather_data = self._fetch_weather(city, unit)
            return {
                "city": city,
                "temperature": weather_data["temp"],
                "condition": weather_data["condition"],
                "humidity": weather_data["humidity"]
            }
        return {"error": f"未知工具: {func_name}"}
    
    def _fetch_weather(self, city: str, unit: str) -> dict:
        # 实际 API 调用逻辑
        import requests
        response = requests.get(
            f"https://api.example.com/weather",
            params={"city": city, "unit": unit, "key": self.api_key}
        )
        return response.json()
```

### 2. EventSubscriber — 事件订阅

订阅系统事件（EventBus），实现自动化流程。

**协议接口**：

```python
from typing import Dict, Callable

class EventSubscriber(Protocol):
    def get_event_subscriptions(self) -> Dict[str, Callable]: ...
```

**完整示例**：

```python
from core.plugin.base import PluginBase, EventSubscriber
from core.adapter.event import PlatformEvent
from core.bus.bus import bus

class AutoReplyPlugin(PluginBase, EventSubscriber):
    def _activate(self) -> None:
        self.keywords = self.get_config("keywords", ["你好", "帮助"])
    
    def _deactivate(self) -> None:
        pass
    
    def get_event_subscriptions(self) -> Dict[str, Callable]:
        return {
            "platform_message_received": self._on_message,
            "adapter_started": self._on_adapter_start,
            "config_reloaded": self._on_config_reload
        }
    
    async def _on_message(self, event: PlatformEvent, adapter_id: str):
        """收到消息时触发"""
        text = event.content.text or ""
        for keyword in self.keywords:
            if keyword in text:
                print(f"[AutoReply] 检测到关键词: {keyword}")
                # 可以通过 bus 发送事件触发回复
                bus.emit("auto_reply_triggered", {
                    "keyword": keyword,
                    "event": event
                })
    
    def _on_adapter_start(self, adapter_id: str):
        """适配器启动时触发"""
        print(f"[AutoReply] 适配器 {adapter_id} 已启动")
    
    def _on_config_reload(self):
        """配置重载时触发"""
        self.keywords = self.get_config("keywords", ["你好", "帮助"])
        print(f"[AutoReply] 配置已更新: {self.keywords}")
```

**常用事件列表**：

| 事件名称 | 触发时机 | 参数 |
|---------|---------|------|
| `platform_message_received` | 收到平台消息 | `event: PlatformEvent, adapter_id: str` |
| `adapter_started` | 适配器启动 | `adapter_id: str` |
| `adapter_stopped` | 适配器停止 | `adapter_id: str` |
| `config_reloaded` | 配置重载 | 无 |
| `pipeline_stage_before_{stage}` | Pipeline Stage 执行前 | `ctx: PipelineContext` |
| `pipeline_stage_after_{stage}` | Pipeline Stage 执行后 | `ctx: PipelineContext` |

### 3. WebUIProvider — WebUI 扩展

添加自定义 WebUI 页面和 API 路由。

**协议接口**：

```python
from typing import List, Dict
from flask import Blueprint

class WebUIProvider(Protocol):
    def get_blueprints(self) -> List[Blueprint]: ...
    def get_nav_items(self) -> List[Dict[str, str]]: ...
```

**完整示例**：

```python
from core.plugin.base import PluginBase, WebUIProvider
from flask import Blueprint, render_template_string, jsonify, request

class DashboardPlugin(PluginBase, WebUIProvider):
    def _activate(self) -> None:
        pass
    
    def _deactivate(self) -> None:
        pass
    
    def get_blueprints(self) -> List[Blueprint]:
        bp = Blueprint("my_dashboard", __name__, url_prefix="/plugin/my_dashboard")
        
        @bp.route("/")
        def index():
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>我的仪表盘</title>
                <link rel="stylesheet" href="/static/css/style.css">
            </head>
            <body>
                <h1>自定义仪表盘</h1>
                <div id="stats"></div>
                <script>
                    fetch('/plugin/my_dashboard/api/stats')
                        .then(r => r.json())
                        .then(data => {
                            document.getElementById('stats').innerText = 
                                JSON.stringify(data, null, 2);
                        });
                </script>
            </body>
            </html>
            """
            return render_template_string(html)
        
        @bp.route("/api/stats")
        def api_stats():
            return jsonify({
                "total_messages": 1234,
                "active_users": 56,
                "uptime": "3 days"
            })
        
        @bp.route("/api/config", methods=["GET", "POST"])
        def api_config():
            if request.method == "POST":
                # 保存配置
                new_config = request.json
                # 调用 PluginManager 更新配置
                return jsonify({"ok": True})
            else:
                # 返回当前配置
                return jsonify(self.config)
        
        return [bp]
    
    def get_nav_items(self) -> List[Dict[str, str]]:
        return [
            {
                "label": "我的仪表盘",
                "href": "/plugin/my_dashboard"
            }
        ]
```

### 4. XMLTagHandler — 自定义 XML 标签

处理 AI 响应中的自定义 XML 标签。

**协议接口**：

```python
from typing import List, Optional, Any
from xml.etree.ElementTree import Element

class XMLTagHandler(Protocol):
    def get_handled_tags(self) -> List[str]: ...
    def handle_tag(self, tag_name: str, element: Element, context: dict) -> Optional[Any]: ...
```

**完整示例**：

```python
from core.plugin.base import PluginBase, XMLTagHandler
from xml.etree.ElementTree import Element

class ImageGenPlugin(PluginBase, XMLTagHandler):
    def _activate(self) -> None:
        pass
    
    def _deactivate(self) -> None:
        pass
    
    def get_handled_tags(self) -> List[str]:
        return ["image", "draw"]
    
    def handle_tag(self, tag_name: str, element: Element, context: dict) -> Optional[Any]:
        """
        当 AI 输出包含 <image>...</image> 或 <draw>...</draw> 时触发
        
        Args:
            tag_name: 标签名（image 或 draw）
            element: XML 元素对象
            context: 上下文信息 {"event": PlatformEvent, "parsed_msg": ParsedMessage}
        
        Returns:
            返回值会被添加到回复内容中
        """
        if tag_name == "image":
            prompt = element.text or ""
            # 调用图片生成 API
            image_url = self._generate_image(prompt)
            return {
                "type": "image",
                "url": image_url,
                "prompt": prompt
            }
        elif tag_name == "draw":
            # 处理绘图请求
            return self._handle_draw(element)
        return None
    
    def _generate_image(self, prompt: str) -> str:
        # 调用 DALL-E / Stable Diffusion 等 API
        import requests
        response = requests.post(
            "https://api.example.com/generate",
            json={"prompt": prompt, "size": "512x512"}
        )
        return response.json()["url"]
    
    def _handle_draw(self, element: Element) -> dict:
        # 解析绘图参数
        shape = element.attrib.get("shape", "circle")
        color = element.attrib.get("color", "blue")
        return {
            "type": "drawing",
            "shape": shape,
            "color": color
        }
```

**AI 使用示例**：

```xml
<msg>好的，我来帮你生成一张图片</msg>
<image>一只可爱的橘猫，坐在窗边晒太阳，水彩风格</image>
```

### 5. PromptSectionProvider — 提示词注入

向 LLM Agent 的 prompt 中注入自定义内容。

**协议接口**：

```python
from typing import List, Tuple
from core.llm.context.section import PromptSection

class PromptSectionProvider(Protocol):
    def get_prompt_sections(self) -> List[Tuple[str, PromptSection]]: ...
```

**完整示例**：

```python
from core.plugin.base import PluginBase, PromptSectionProvider
from core.llm.context.section import PromptSection

class MemoryPlugin(PluginBase, PromptSectionProvider):
    def _activate(self) -> None:
        self.memory_db = {}  # 简化示例，实际应使用数据库
    
    def _deactivate(self) -> None:
        pass
    
    def get_prompt_sections(self) -> List[Tuple[str, PromptSection]]:
        """
        返回 (agent_name, PromptSection) 元组列表
        agent_name 可选值: "chat", "tool", "plan"
        """
        return [
            ("chat", PromptSection(
                name="long_term_memory",
                content=self._build_memory_prompt(),
                order=150,  # 在基础 prompt 之后
                cacheable=True
            )),
            ("plan", PromptSection(
                name="plan_memory",
                content="## 历史计划记忆\n\n用户通常在早上 9 点开始工作。",
                order=200,
                cacheable=False
            ))
        ]
    
    def _build_memory_prompt(self) -> str:
        # 动态构建记忆 prompt
        memories = self.memory_db.get("user_123", [])
        if not memories:
            return ""
        
        prompt = "## 长期记忆\n\n"
        prompt += "你记得以下信息：\n"
        for mem in memories:
            prompt += f"- {mem}\n"
        return prompt
```

**PromptSection 参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | Section 唯一标识 |
| `content` | `str` | Prompt 内容 |
| `order` | `int` | 排序优先级（越小越靠前） |
| `cacheable` | `bool` | 是否可被 Anthropic Prompt Caching 缓存 |

### 6. 多扩展点组合

一个插件可以同时实现多个扩展点。

```python
from core.plugin.base import PluginBase, ToolProvider, EventSubscriber, WebUIProvider

class SuperPlugin(PluginBase, ToolProvider, EventSubscriber, WebUIProvider):
    """实现工具、事件、WebUI 三个扩展点"""
    
    def _activate(self) -> None:
        self.stats = {"tool_calls": 0, "events": 0}
    
    def _deactivate(self) -> None:
        pass
    
    # ToolProvider
    def get_tool_definitions(self) -> List[ToolDefinition]:
        return [...]
    
    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        self.stats["tool_calls"] += 1
        return {"result": "success"}
    
    # EventSubscriber
    def get_event_subscriptions(self) -> Dict[str, Callable]:
        return {
            "platform_message_received": self._on_message
        }
    
    async def _on_message(self, event, adapter_id):
        self.stats["events"] += 1
    
    # WebUIProvider
    def get_blueprints(self) -> List[Blueprint]:
        bp = Blueprint("super_plugin", __name__)
        
        @bp.route("/stats")
        def stats():
            return jsonify(self.stats)
        
        return [bp]
    
    def get_nav_items(self) -> List[Dict[str, str]]:
        return [{"label": "Super Plugin", "href": "/stats"}]
```

## 配置管理

### 运行时配置

插件的配置存储在 `data/config/plugins.yaml`：

```yaml
my_plugin:
  enabled: true
  config:
    api_key: "sk-xxxxxx"
    enable_cache: true
    log_level: "INFO"
```

### 读取配置

```python
class MyPlugin(PluginBase):
    def _activate(self) -> None:
        # 读取配置项（带默认值）
        self.api_key = self.get_config("api_key", "")
        self.cache_enabled = self.get_config("enable_cache", True)
        self.log_level = self.get_config("log_level", "INFO")
        
        # 校验必需配置
        if not self.api_key:
            raise ValueError("api_key is required")
```

### 动态更新配置

用户在 WebUI 修改配置后，系统会：
1. 保存到 `plugins.yaml`
2. 触发 `config_reloaded` 事件
3. 插件在事件回调中重新加载配置

```python
def get_event_subscriptions(self) -> Dict[str, Callable]:
    return {
        "config_reloaded": self._reload_config
    }

def _reload_config(self):
    self.api_key = self.get_config("api_key", "")
    print(f"[MyPlugin] 配置已更新: {self.api_key[:8]}...")
```

## 调试方法

### 1. 日志输出

```python
from core.utils import get_logger

logger = get_logger(__name__)

class MyPlugin(PluginBase):
    def _activate(self) -> None:
        logger.info("[MyPlugin] 插件已激活")
        logger.debug(f"配置: {self.config}")
    
    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        logger.info(f"[MyPlugin] 执行工具: {func_name}, 参数: {parameters}")
        try:
            result = self._do_work(parameters)
            logger.debug(f"[MyPlugin] 工具结果: {result}")
            return result
        except Exception as e:
            logger.error(f"[MyPlugin] 工具执行失败: {e}", exc_info=True)
            raise
```

### 2. 本地测试

创建测试脚本 `test_plugin.py`：

```python
import asyncio
from pathlib import Path
from core.plugin.manager import PluginManager

async def test_my_plugin():
    # 初始化插件管理器
    manager = PluginManager(
        plugins_dir=Path("plugins"),
        config={
            "my_plugin": {
                "enabled": True,
                "config": {
                    "api_key": "test_key_123"
                }
            }
        }
    )
    
    # 加载插件
    success = manager.load_plugin("my_plugin")
    print(f"插件加载: {'成功' if success else '失败'}")
    
    # 测试工具调用
    plugin = manager._plugins.get("my_plugin")
    if plugin:
        result = plugin.execute_tool("my_tool", {"param": "value"})
        print(f"工具结果: {result}")
    
    # 卸载插件
    manager.unload_plugin("my_plugin")

if __name__ == "__main__":
    asyncio.run(test_my_plugin())
```

### 3. WebUI 调试

1. 启动 Tale-AI：`python main.py`
2. 访问 `http://localhost:32456/plugins`
3. 上传插件 ZIP 或启用已安装插件
4. 查看日志输出：`http://localhost:32456/logs`

### 4. 单元测试

```python
import pytest
from core.plugin.base import PluginManifest
from plugins.my_plugin.plugin import MyPlugin

@pytest.fixture
def plugin():
    manifest = PluginManifest(
        id="my_plugin",
        name="Test Plugin",
        version="1.0.0"
    )
    config = {"api_key": "test_key"}
    return MyPlugin(manifest, config)

def test_tool_execution(plugin):
    plugin.activate()
    result = plugin.execute_tool("my_tool", {"city": "北京"})
    assert result["city"] == "北京"
    plugin.deactivate()

@pytest.mark.asyncio
async def test_event_handler(plugin):
    plugin.activate()
    # 模拟事件
    from core.adapter.event import PlatformEvent, PlatformType, EventType
    event = PlatformEvent(
        platform=PlatformType.QQ,
        event_type=EventType.PRIVATE_MESSAGE,
        sender=...,
        content=...
    )
    await plugin._on_message(event, "qq_adapter")
    plugin.deactivate()
```

## 打包与分发

### 创建插件包

```bash
# 项目结构
my_plugin/
├── manifest.json
├── plugin.py
├── schema.json
└── README.md

# 打包为 ZIP
cd plugins
zip -r my_plugin.zip my_plugin/
```

### 安装插件

**方式 1：WebUI 上传**
1. 访问 `http://localhost:32456/plugins`
2. 点击"上传插件"按钮
3. 选择 ZIP 文件上传

**方式 2：手动安装**
```bash
# 解压到 plugins 目录
unzip my_plugin.zip -d plugins/
# 重启 Tale-AI
python main.py
```

**方式 3：API 安装**
```python
import requests

files = {"file": open("my_plugin.zip", "rb")}
response = requests.post(
    "http://localhost:32456/api/plugins/install",
    files=files,
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
print(response.json())
```

## 最佳实践

### 1. 错误处理

```python
def execute_tool(self, func_name: str, parameters: dict) -> Any:
    try:
        result = self._risky_operation(parameters)
        return {"success": True, "data": result}
    except ValueError as e:
        return {"success": False, "error": f"参数错误: {e}"}
    except TimeoutError:
        return {"success": False, "error": "请求超时"}
    except Exception as e:
        logger.error(f"未预期的错误: {e}", exc_info=True)
        return {"success": False, "error": "内部错误"}
```

### 2. 资源清理

```python
def _activate(self) -> None:
    self.db_conn = create_connection()
    self.cache = {}

def _deactivate(self) -> None:
    # 清理资源
    if hasattr(self, "db_conn"):
        self.db_conn.close()
    if hasattr(self, "cache"):
        self.cache.clear()
```

### 3. 性能优化

```python
from functools import lru_cache
import asyncio

class MyPlugin(PluginBase):
    @lru_cache(maxsize=128)
    def _expensive_computation(self, key: str) -> str:
        # 缓存计算结果
        return self._do_heavy_work(key)
    
    async def execute_tool_async(self, func_name: str, parameters: dict):
        # 异步执行避免阻塞
        result = await asyncio.to_thread(self._blocking_call, parameters)
        return result
```

### 4. 安全性

```python
def execute_tool(self, func_name: str, parameters: dict) -> Any:
    # 输入校验
    city = parameters.get("city", "").strip()
    if not city or len(city) > 50:
        return {"error": "城市名称无效"}
    
    # SQL 注入防护（使用参数化查询）
    cursor.execute("SELECT * FROM weather WHERE city = ?", (city,))
    
    # 路径遍历防护
    safe_path = os.path.normpath(file_path)
    if not safe_path.startswith(ALLOWED_DIR):
        return {"error": "非法路径"}
```

### 5. 文档完善

在 `README.md` 中提供：
- 插件功能说明
- 配置项详解
- 使用示例
- 常见问题

```markdown
# My Plugin

## 功能

提供天气查询功能。

## 配置

```yaml
my_plugin:
  enabled: true
  config:
    api_key: "your_api_key"  # 从 https://example.com 获取
    cache_ttl: 3600          # 缓存有效期（秒）
```

## 使用

AI 会自动调用 `get_weather` 工具：

用户：北京今天天气怎么样？
AI：<msg>让我查一下</msg><tool>get_weather</tool>
```

## 常见问题

### Q: 插件加载失败

**A**: 检查以下几点：
1. `manifest.json` 格式是否正确（使用 JSON 校验器）
2. `plugin.py` 中的类名是否与 `manifest.json` 的 `class` 字段一致
3. 是否继承了 `PluginBase`
4. `_activate` 和 `_deactivate` 方法是否正确实现

### Q: 工具未被 AI 调用

**A**: 确保：
1. `get_tool_definitions()` 返回的 `ToolDefinition` 包含清晰的 `description`
2. `parameters` schema 符合 OpenAI Function Calling 规范
3. 插件已启用（`plugins.yaml` 中 `enabled: true`）
4. ToolLLM 已重建工具定义（重启 Tale-AI 或调用 `toolllm.rebuild_tool_definitions()`）

### Q: 如何调试事件未触发

**A**: 
1. 在 `_on_message` 等回调函数开头添加 `logger.info` 确认是否被调用
2. 检查事件名称是否正确（区分大小写）
3. 使用 `bus.emit()` 手动触发事件进行测试

### Q: 配置修改后未生效

**A**:
1. 确认配置已保存到 `data/config/plugins.yaml`
2. 重启 Tale-AI 或触发配置重载
3. 在插件中订阅 `config_reloaded` 事件并重新读取配置

## 下一步

- [适配器开发](adapter-development.md) — 开发平台适配器
- [贡献指南](contributing.md) — 向 Tale-AI 贡献代码
- [Pipeline 系统](../architecture/pipeline.md) — 理解消息处理流程
