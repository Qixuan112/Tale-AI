from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


class HookType(Enum):
    TOOL = "tool"
    EVENT = "event"
    WEBUI_PAGE = "webui_page"
    WEBUI_API = "webui_api"
    XML_TAG = "xml_tag"
    PROMPT_SECTION = "prompt_section"


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    module: str = "plugin"
    class_name: str = ""
    hooks: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    min_tale_version: str = "1.0.0"
    builtin: bool = False
    requirements: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "PluginManifest":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "0.1.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            module=data.get("module", "plugin"),
            class_name=data.get("class", ""),
            hooks=data.get("hooks", []),
            dependencies=data.get("dependencies", {}),
            min_tale_version=data.get("min_tale_version", "1.0.0"),
            builtin=data.get("builtin", False),
            requirements=data.get("requirements", []),
        )


# ----- Extension point protocols -----

@runtime_checkable
class ToolProvider(Protocol):
    """Plugin provides custom tools."""
    def get_tool_definitions(self) -> List[Any]: ...
    def execute_tool(self, func_name: str, parameters: dict) -> Any: ...


@runtime_checkable
class EventSubscriber(Protocol):
    """Plugin subscribes to EventBus events."""
    def get_event_subscriptions(self) -> Dict[str, Callable]: ...


@runtime_checkable
class WebUIProvider(Protocol):
    """Plugin adds WebUI pages or API routes."""
    def get_blueprints(self) -> List[Any]: ...
    def get_nav_items(self) -> List[Dict[str, str]]: ...


@runtime_checkable
class XMLTagHandler(Protocol):
    """Plugin handles custom XML tags in AI replies."""
    def get_handled_tags(self) -> List[str]: ...
    def handle_tag(self, tag_name: str, element: Any, context: dict) -> Optional[Any]: ...


@runtime_checkable
class PromptSectionProvider(Protocol):
    """Plugin adds prompt sections to LLM agent contexts."""
    def get_prompt_sections(self) -> List[tuple]: ...


# ----- Plugin base class -----

class PluginBase(ABC):
    """Base class for all Tale-AI plugins.

    Subclasses implement ``_activate()`` and ``_deactivate()``, and optionally
    implement one or more extension point protocols.
    """

    def __init__(self, manifest: PluginManifest, plugin_config: Optional[Dict[str, Any]] = None):
        self.manifest = manifest
        self.config = plugin_config or {}
        self._active = False

    # ---- Lifecycle ----

    @abstractmethod
    def _activate(self) -> None:
        """Register hooks with the system."""

    @abstractmethod
    def _deactivate(self) -> None:
        """Clean up hooks."""

    def activate(self) -> None:
        if self._active:
            return
        self._activate()
        self._active = True

    def deactivate(self) -> None:
        if not self._active:
            return
        self._deactivate()
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    # ---- Helpers ----

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def __repr__(self) -> str:
        return f"<{self.manifest.id} v{self.manifest.version} active={self._active}>"
