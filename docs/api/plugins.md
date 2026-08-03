# Plugin API 参考

Tale-AI 插件系统提供 6 个扩展点，支持工具、事件、WebUI、XML 标签、Prompt 段落的动态扩展。

**核心模块**: `core/plugin/`

---

## 核心类

### PluginBase

所有插件的抽象基类。

**定义位置**: `core/plugin/base.py`

#### 构造函数

```python
def __init__(self, manifest: PluginManifest, plugin_config: Optional[Dict[str, Any]] = None):
    """
    Args:
        manifest: 插件清单（从 manifest.json 解析）
        plugin_config: 插件配置（从 plugins.yaml 加载，已与 schema.json 合并）
    """
```

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `manifest` | `PluginManifest` | 插件清单（id, name, version, hooks 等） |
| `config` | `Dict[str, Any]` | 插件配置字典 |
| `_active` | `bool` | 激活状态（私有，通过 `is_active` 访问） |

#### 抽象方法（必须实现）

```python
@abstractmethod
def _activate(self) -> None:
    """注册 hooks（由 PluginManager 调用）
    
    在此方法中完成插件的初始化工作。
    PluginManager 会自动处理扩展点的注册，无需手动调用 EventBus/ToolRegistry。
    """

@abstractmethod
def _deactivate(self) -> None:
    """清理 hooks（由 PluginManager 调用）
    
    在此方法中完成插件的清理工作。
    PluginManager 会自动处理扩展点的反注册。
    """
```

#### 公开方法

```python
def activate(self) -> None:
    """激活插件（幂等操作）"""

def deactivate(self) -> None:
    """停用插件（幂等操作）"""

@property
def is_active(self) -> bool:
    """返回插件是否已激活"""

def get_config(self, key: str, default: Any = None) -> Any:
    """获取配置项
    
    Args:
        key: 配置键
        default: 默认值
        
    Returns:
        配置值或默认值
    """
```

---

### PluginManifest

插件清单数据类，从 `manifest.json` 解析。

**定义位置**: `core/plugin/base.py`

#### 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | `str` | - | 必填。插件唯一 ID（如 `echo_tool`） |
| `name` | `str` | - | 必填。插件显示名称 |
| `version` | `str` | - | 必填。语义化版本号（如 `1.0.0`） |
| `author` | `str` | `""` | 作者 |
| `description` | `str` | `""` | 插件描述 |
| `module` | `str` | `"plugin"` | 入口模块名（默认 `plugin.py`） |
| `class_name` | `str` | `""` | 插件类名（空则自动查找 `PluginBase` 子类） |
| `hooks` | `List[str]` | `[]` | 实现的扩展点列表（如 `["tool", "event"]`） |
| `dependencies` | `Dict[str, str]` | `{}` | 依赖的其他插件（预留，暂未实现） |
| `min_tale_version` | `str` | `"1.0.0"` | 最低 Tale-AI 版本要求 |
| `builtin` | `bool` | `False` | 是否为内置插件 |
| `requirements` | `List[str]` | `[]` | Python 依赖包列表（如 `["requests>=2.28.0"]`） |

#### 示例 manifest.json

```json
{
  "id": "my_plugin",
  "name": "My Awesome Plugin",
  "version": "1.0.0",
  "author": "Alice",
  "description": "A plugin that does awesome things",
  "module": "plugin",
  "class": "MyPlugin",
  "hooks": ["tool", "event"],
  "min_tale_version": "1.0.0",
  "builtin": false,
  "requirements": ["aiohttp>=3.8.0"]
}
```

---

## 扩展点协议

插件通过实现以下 Protocol 扩展系统功能。每个协议是独立的，可任意组合。

### 1. ToolProvider

提供自定义工具供 AI 调用。

**定义位置**: `core/plugin/base.py`

```python
@runtime_checkable
class ToolProvider(Protocol):
    """插件提供自定义工具"""
    
    def get_tool_definitions(self) -> List[Any]:
        """返回工具定义列表
        
        Returns:
            List[ToolDefinition]: 工具定义对象列表
            
        注意:
            ToolDefinition 需包含 name, description, parameters 字段
        """
        ...
    
    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        """执行工具调用
        
        Args:
            func_name: 工具名（对应 ToolDefinition.name）
            parameters: 参数字典
            
        Returns:
            工具执行结果（任意类型，会转为字符串）
            
        Raises:
            Exception: 执行失败时抛出
        """
        ...
```

**示例**:

```python
from core.plugin.base import PluginBase, ToolProvider
from core.tools.registry import ToolDefinition, ToolParameter

class EchoToolPlugin(PluginBase, ToolProvider):
    def get_tool_definitions(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="echo",
                description="返回输入的文本",
                parameters=[
                    ToolParameter(
                        name="text",
                        type="string",
                        description="要回显的文本",
                        required=True
                    )
                ]
            )
        ]
    
    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        if func_name == "echo":
            return f"Echo: {parameters['text']}"
        raise ValueError(f"Unknown tool: {func_name}")
    
    def _activate(self):
        pass  # PluginManager 自动注册工具
    
    def _deactivate(self):
        pass
```

---

### 2. EventSubscriber

订阅 EventBus 事件。

**定义位置**: `core/plugin/base.py`

```python
@runtime_checkable
class EventSubscriber(Protocol):
    """插件订阅 EventBus 事件"""
    
    def get_event_subscriptions(self) -> Dict[str, Callable]:
        """返回事件订阅字典
        
        Returns:
            Dict[str, Callable]: {事件名: 回调函数}
            
        注意:
            - 回调函数支持同步/异步
            - PluginManager 自动调用 bus.on() 注册
        """
        ...
```

**示例**:

```python
from core.plugin.base import PluginBase, EventSubscriber

class LoggerPlugin(PluginBase, EventSubscriber):
    def get_event_subscriptions(self) -> Dict[str, Callable]:
        return {
            "config_reloaded": self.on_config_reload,
            "message": self.on_message,
        }
    
    def on_config_reload(self):
        print("Config was reloaded")
    
    async def on_message(self, text, sender):
        await self.log_to_file(text, sender)
    
    def _activate(self):
        pass
    
    def _deactivate(self):
        pass
```

---

### 3. WebUIProvider

添加 WebUI 页面和 API 路由。

**定义位置**: `core/plugin/base.py`

```python
@runtime_checkable
class WebUIProvider(Protocol):
    """插件添加 WebUI 页面或 API 路由"""
    
    def get_blueprints(self) -> List[Any]:
        """返回 Flask Blueprint 列表
        
        Returns:
            List[flask.Blueprint]: Flask Blueprint 对象列表
        """
        ...
    
    def get_nav_items(self) -> List[Dict[str, str]]:
        """返回导航栏项列表
        
        Returns:
            List[Dict]: 导航项，每项包含 label, href, icon（可选）
            
        示例:
            [{"label": "My Page", "href": "/plugin/my-page", "icon": "fa-cog"}]
        """
        ...
```

**示例**:

```python
from flask import Blueprint, render_template
from core.plugin.base import PluginBase, WebUIProvider

my_bp = Blueprint("my_plugin", __name__, url_prefix="/plugin/my")

@my_bp.route("/dashboard")
def dashboard():
    return render_template("my_plugin/dashboard.html")

@my_bp.route("/api/data")
def api_data():
    return {"status": "ok", "data": [1, 2, 3]}

class MyWebUIPlugin(PluginBase, WebUIProvider):
    def get_blueprints(self):
        return [my_bp]
    
    def get_nav_items(self):
        return [
            {"label": "My Dashboard", "href": "/plugin/my/dashboard", "icon": "fa-dashboard"}
        ]
    
    def _activate(self):
        pass
    
    def _deactivate(self):
        pass
```

---

### 4. XMLTagHandler

处理 AI 回复中的自定义 XML 标签。

**定义位置**: `core/plugin/base.py`

```python
@runtime_checkable
class XMLTagHandler(Protocol):
    """插件处理自定义 XML 标签"""
    
    def get_handled_tags(self) -> List[str]:
        """返回处理的标签名列表
        
        Returns:
            List[str]: XML 标签名列表（如 ["task", "reminder"]）
        """
        ...
    
    def handle_tag(self, tag_name: str, element: Any, context: dict) -> Optional[Any]:
        """处理 XML 标签
        
        Args:
            tag_name: 标签名
            element: xml.etree.ElementTree.Element 对象
            context: 上下文信息（包含 platform, sender_id 等）
            
        Returns:
            处理结果（可选）
            
        注意:
            - element.text 获取标签内容
            - element.attrib 获取属性字典
        """
        ...
```

**示例**:

```python
from core.plugin.base import PluginBase, XMLTagHandler
import xml.etree.ElementTree as ET

class TaskPlugin(PluginBase, XMLTagHandler):
    def get_handled_tags(self):
        return ["task"]
    
    def handle_tag(self, tag_name: str, element: ET.Element, context: dict) -> None:
        if tag_name == "task":
            title = element.attrib.get("title", "Untitled")
            description = element.text or ""
            deadline = element.attrib.get("deadline")
            
            # 创建任务
            self.create_task(title, description, deadline)
            print(f"Task created: {title}")
    
    def create_task(self, title, description, deadline):
        pass  # 实际任务创建逻辑
    
    def _activate(self):
        pass
    
    def _deactivate(self):
        pass
```

**AI 回复示例**:

```xml
<msg>好的，我帮你创建任务</msg>
<task title="写报告" deadline="2026-08-10">完成 Q3 季度报告</task>
```

---

### 5. PromptSectionProvider

向 LLM Agent 添加自定义 Prompt 段落。

**定义位置**: `core/plugin/base.py`

```python
@runtime_checkable
class PromptSectionProvider(Protocol):
    """插件添加 Prompt 段落"""
    
    def get_prompt_sections(self) -> List[tuple]:
        """返回 Prompt 段落列表
        
        Returns:
            List[Tuple[str, PromptSection]]: [(agent_name, section), ...]
            
        agent_name 可选值:
            - "chat": ChatLLM
            - "tool": ToolLLM
            - "plan": PlanLLM
            
        注意:
            - PromptSection 需包含 content, order, cacheable 字段
            - PluginManager 会调用 agent.context.add_section(section)
        """
        ...
```

**示例**:

```python
from core.plugin.base import PluginBase, PromptSectionProvider
from core.llm.context.section import PromptSection

class CustomPromptPlugin(PluginBase, PromptSectionProvider):
    def get_prompt_sections(self):
        return [
            ("chat", PromptSection(
                content="你现在可以使用 <task> 标签创建任务。",
                order=50,
                cacheable=False
            )),
            ("tool", PromptSection(
                content="Tool calling instructions...",
                order=100,
                cacheable=True
            ))
        ]
    
    def _activate(self):
        pass
    
    def _deactivate(self):
        pass
```

---

## PluginManager

插件管理器，负责插件的发现、加载、生命周期管理。

**定义位置**: `core/plugin/manager.py`

### 构造函数

```python
def __init__(
    self,
    plugins_dir: Optional[Path] = None,
    config: Optional[Dict[str, PluginRuntimeConfig]] = None,
):
    """
    Args:
        plugins_dir: 插件目录（默认 core/../plugins）
        config: 插件运行时配置（从 plugins.yaml 加载）
    """
```

### 生命周期方法

```python
def load_plugin(self, plugin_id: str) -> bool:
    """加载单个插件
    
    Args:
        plugin_id: 插件 ID（对应 manifest.json 的 id 字段）
        
    Returns:
        True: 加载成功
        False: 加载失败或插件已禁用
        
    注意:
        - 自动调用 plugin.activate()
        - 线程安全（内部使用 _class_lock）
    """

def unload_plugin(self, plugin_id: str) -> bool:
    """卸载单个插件
    
    Args:
        plugin_id: 插件 ID
        
    Returns:
        True: 卸载成功或插件未加载
        
    注意:
        - 自动调用 plugin.deactivate()
        - 自动反注册所有扩展点
    """

def load_all_enabled(self) -> Dict[str, bool]:
    """加载所有已启用的插件
    
    Returns:
        Dict[str, bool]: {plugin_id: 是否加载成功}
    """

def unload_all(self) -> None:
    """卸载所有已加载的插件"""
```

### 安装方法

```python
def install_from_zip(
    self,
    zip_path: Path,
    target_dir: Path,
    toolllm=None
) -> dict:
    """从 ZIP 安装插件
    
    Args:
        zip_path: ZIP 文件路径
        target_dir: 目标目录（通常是 plugins_dir）
        toolllm: ToolLLM 实例（用于重建工具定义）
        
    Returns:
        Dict: {"ok": bool, "plugin_id": str, "error": str}
        
    注意:
        - 自动解压、扫描、加载插件
        - 覆盖安装时会先卸载旧版本
        - 内置插件不允许被覆盖
        - 安全检查：路径遍历、符号链接
    """
```

### 查询方法

```python
@classmethod
def list_available(cls) -> List[PluginManifest]:
    """列出所有可用插件（包括未加载的）
    
    Returns:
        List[PluginManifest]: 插件清单列表
    """

@classmethod
def get_plugin_info(cls, plugin_id: str) -> Optional[dict]:
    """获取插件详细信息
    
    Args:
        plugin_id: 插件 ID
        
    Returns:
        Dict 包含 manifest 和 schema，或 None
    """

def list_loaded(self) -> List[str]:
    """列出已加载的插件 ID
    
    Returns:
        List[str]: 插件 ID 列表
    """

def is_loaded(self, plugin_id: str) -> bool:
    """检查插件是否已加载
    
    Args:
        plugin_id: 插件 ID
        
    Returns:
        True: 已加载
    """
```

---

## 插件配置

### plugins.yaml 格式

```yaml
plugins:
  my_plugin:
    enabled: true  # 是否启用
    config:
      api_key: "sk-xxx"
      timeout: 30
      debug: false
```

### schema.json 格式

定义插件的配置项 schema，支持默认值。

```json
[
  {
    "name": "api_key",
    "type": "string",
    "description": "API Key",
    "default": "",
    "required": true
  },
  {
    "name": "timeout",
    "type": "integer",
    "description": "超时时间（秒）",
    "default": 30,
    "required": false
  },
  {
    "name": "debug",
    "type": "boolean",
    "description": "调试模式",
    "default": false,
    "required": false
  }
]
```

**配置合并逻辑**:
1. 从 `schema.json` 读取默认值
2. 从 `plugins.yaml` 读取运行时配置
3. 运行时配置覆盖默认值
4. 最终配置传递给 `PluginBase.__init__(manifest, plugin_config)`

---

## 插件目录结构

```
plugins/
└── my_plugin/
    ├── manifest.json       # 必填。插件清单
    ├── schema.json         # 可选。配置 schema
    ├── plugin.py           # 必填。插件入口
    ├── __init__.py         # 可选。包初始化
    ├── requirements.txt    # 可选。Python 依赖
    └── templates/          # 可选。WebUI 模板
        └── my_page.html
```

**最小插件示例**:

```python
# plugins/hello/manifest.json
{
  "id": "hello",
  "name": "Hello Plugin",
  "version": "1.0.0",
  "hooks": ["event"]
}

# plugins/hello/plugin.py
from core.plugin.base import PluginBase, EventSubscriber

class HelloPlugin(PluginBase, EventSubscriber):
    def get_event_subscriptions(self):
        return {"app_start": self.on_start}
    
    def on_start(self):
        print("Hello from plugin!")
    
    def _activate(self):
        pass
    
    def _deactivate(self):
        pass
```

---

## 生命周期钩子

插件生命周期：

```
未加载 -> 加载中 -> 已激活 -> 停用中 -> 已卸载
   ↑                                     ↓
   └─────────────────────────────────────┘
```

**阶段说明**:

1. **未加载**: 插件目录已扫描，manifest 已解析，但模块未导入
2. **加载中**: 
   - 导入 `plugin.py`
   - 实例化 `PluginBase` 子类
   - 调用 `_activate()`
   - 注册扩展点（ToolProvider, EventSubscriber 等）
3. **已激活**: 插件正常运行，扩展点已生效
4. **停用中**:
   - 调用 `_deactivate()`
   - 反注册扩展点
5. **已卸载**: 插件实例已销毁，扩展点已清理

**方法调用顺序**:

```python
# 加载
manager.load_plugin("my_plugin")
  -> plugin = MyPlugin(manifest, config)
  -> plugin._activate()  # 子类实现
  -> plugin.activate()   # 标记为已激活
  -> # PluginManager 自动注册扩展点

# 卸载
manager.unload_plugin("my_plugin")
  -> plugin.deactivate() # 标记为已停用
  -> plugin._deactivate()  # 子类实现
  -> # PluginManager 自动反注册扩展点
```

---

## 完整插件示例

```python
# plugins/demo/manifest.json
{
  "id": "demo",
  "name": "Demo Plugin",
  "version": "1.0.0",
  "author": "Tale Team",
  "description": "演示所有扩展点的插件",
  "hooks": ["tool", "event", "webui", "xml_tag", "prompt_section"],
  "requirements": []
}

# plugins/demo/plugin.py
from typing import Any, Callable, Dict, List
from flask import Blueprint
from core.plugin.base import (
    PluginBase, ToolProvider, EventSubscriber, 
    WebUIProvider, XMLTagHandler, PromptSectionProvider
)
from core.tools.registry import ToolDefinition, ToolParameter
from core.llm.context.section import PromptSection
import xml.etree.ElementTree as ET

# Flask Blueprint
demo_bp = Blueprint("demo", __name__, url_prefix="/plugin/demo")

@demo_bp.route("/")
def index():
    return "Demo Plugin Home"

class DemoPlugin(
    PluginBase,
    ToolProvider,
    EventSubscriber,
    WebUIProvider,
    XMLTagHandler,
    PromptSectionProvider
):
    # ===== ToolProvider =====
    def get_tool_definitions(self):
        return [
            ToolDefinition(
                name="demo_tool",
                description="演示工具",
                parameters=[
                    ToolParameter(name="text", type="string", description="输入", required=True)
                ]
            )
        ]
    
    def execute_tool(self, func_name: str, parameters: dict) -> Any:
        if func_name == "demo_tool":
            return f"Demo: {parameters['text']}"
        raise ValueError(f"Unknown tool: {func_name}")
    
    # ===== EventSubscriber =====
    def get_event_subscriptions(self) -> Dict[str, Callable]:
        return {
            "config_reloaded": self.on_config_reload,
        }
    
    def on_config_reload(self):
        print("Demo plugin: config reloaded")
    
    # ===== WebUIProvider =====
    def get_blueprints(self):
        return [demo_bp]
    
    def get_nav_items(self):
        return [{"label": "Demo", "href": "/plugin/demo", "icon": "fa-plug"}]
    
    # ===== XMLTagHandler =====
    def get_handled_tags(self):
        return ["demo"]
    
    def handle_tag(self, tag_name: str, element: ET.Element, context: dict):
        if tag_name == "demo":
            print(f"Demo tag: {element.text}")
    
    # ===== PromptSectionProvider =====
    def get_prompt_sections(self):
        return [
            ("chat", PromptSection(
                content="你现在可以使用 <demo> 标签。",
                order=50,
                cacheable=False
            ))
        ]
    
    # ===== 生命周期 =====
    def _activate(self):
        print("Demo plugin activated")
    
    def _deactivate(self):
        print("Demo plugin deactivated")
```

---

## 最佳实践

1. **单一职责**: 每个插件专注解决一个问题
2. **优雅降级**: `_activate()` 失败时应抛出异常，而非静默失败
3. **配置验证**: 在 `_activate()` 中验证必填配置
4. **资源清理**: 在 `_deactivate()` 中释放资源（文件句柄、网络连接等）
5. **错误处理**: 扩展点方法应捕获异常，避免影响核心系统
6. **文档完善**: 在 manifest.json 的 description 中说明插件功能
7. **版本兼容**: 设置合理的 `min_tale_version`
8. **依赖管理**: 在 `requirements` 中列出 Python 依赖

---

## 常见问题

### Q: 插件加载失败怎么办？

A: 检查日志输出，常见原因：
- `manifest.json` 格式错误
- `plugin.py` 中没有 `PluginBase` 子类
- `_activate()` 抛出异常
- 缺少 Python 依赖

### Q: 如何调试插件？

A: 
1. 在 `_activate()` 中添加日志输出
2. 使用 `manager.load_plugin("plugin_id")` 手动加载
3. 检查 PluginManager 日志（级别：INFO/ERROR）

### Q: 插件如何访问核心系统？

A: 
- 通过 `from core.bus import bus` 访问 EventBus
- 通过 `from core.config.provide import config_loader` 访问配置
- 通过依赖注入传递核心对象（如 ToolLLM, ChatLLM）

### Q: 插件可以依赖其他插件吗？

A: `manifest.json` 支持 `dependencies` 字段，但当前版本未实现依赖解析。建议通过 EventBus 松耦合通信。

---

## 参考示例

- **内置插件**: `plugins/echo_tool/` — 演示 ToolProvider
- **最小插件**: 本文档中的 "hello" 示例
- **完整插件**: 本文档中的 "demo" 示例
