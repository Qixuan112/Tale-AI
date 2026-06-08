import json
import os
import shutil
import sys
import importlib.util
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from .base import (
    HookType,
    PluginBase,
    PluginManifest,
    EventSubscriber,
    PromptSectionProvider,
    ToolProvider,
    WebUIProvider,
    XMLTagHandler,
)
from .config import PluginRuntimeConfig, load_plugins_config
from .errors import PluginActivateError, PluginDependencyError, PluginLoadError
from ..utils import get_logger

logger = get_logger(__name__)


class PluginManager:
    """Manages plugin discovery, lifecycle, and extension point wiring.

    Class-level registry (shared across instances) mirrors AdapterManager's pattern:
    ``_registry``, ``_manifests``, ``_schemas``, ``_scanned_dirs``.
    """

    _registry: Dict[str, Type[PluginBase]] = {}
    _manifests: Dict[str, PluginManifest] = {}
    _schemas: Dict[str, list] = {}
    _scanned_dirs: set = set()

    _nav_items: List[Dict[str, str]] = []

    def __init__(
        self,
        plugins_dir: Optional[Path] = None,
        config: Optional[Dict[str, PluginRuntimeConfig]] = None,
    ):
        if plugins_dir is None:
            plugins_dir = Path(__file__).parent.parent / "plugins"
        self._plugins_dir = plugins_dir
        self._runtime_configs = self._normalize_configs(config or {})
        self._plugins: Dict[str, PluginBase] = {}
        self._hook_registrations: Dict[str, Dict[str, list]] = {}
        self._pending_prompt_sections: Dict[str, List[tuple]] = {}

        self._scan_plugins(plugins_dir)

    @staticmethod
    def _normalize_configs(config: dict) -> Dict[str, PluginRuntimeConfig]:
        """Normalize raw dicts to PluginRuntimeConfig objects."""
        normalized = {}
        for pid, cfg in config.items():
            if isinstance(cfg, PluginRuntimeConfig):
                normalized[pid] = cfg
            elif isinstance(cfg, dict):
                normalized[pid] = PluginRuntimeConfig.from_dict(pid, cfg)
            else:
                normalized[pid] = cfg
        return normalized

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    @classmethod
    def _load_plugin_module(cls, plugin_dir: Path) -> Optional[str]:
        """Load manifest + module for a single plugin directory.

        Side effects: populates ``_manifests``, ``_schemas``, ``_registry``.

        Returns the manifest id on success, or None on failure.
        """
        plugin_id = plugin_dir.name
        manifest_path = plugin_dir / "manifest.json"
        schema_path = plugin_dir / "schema.json"
        module_file = plugin_dir / "plugin.py"

        # 1. Parse manifest
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            manifest = PluginManifest.from_dict(raw)
            manifest_id = manifest.id or plugin_id
            cls._manifests[manifest_id] = manifest
        except Exception as e:
            logger.warning("Failed to load manifest for %s: %s", plugin_id, e)
            return None

        # 2. Parse schema (best-effort)
        if schema_path.exists():
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    cls._schemas[manifest_id] = json.load(f)
            except Exception:
                cls._schemas[manifest_id] = []
        else:
            cls._schemas[manifest_id] = []

        # 3. Module required
        if not module_file.exists():
            logger.warning("Plugin %s has no plugin.py", plugin_id)
            return None

        # 4. Import module → find PluginBase subclass
        try:
            package_name = f"plugins.{plugin_id}"
            module_name = f"{package_name}.plugin"

            if package_name not in sys.modules:
                init_file = plugin_dir / "__init__.py"
                if init_file.exists():
                    init_spec = importlib.util.spec_from_file_location(
                        package_name, init_file,
                        submodule_search_locations=[str(plugin_dir)],
                    )
                    init_module = importlib.util.module_from_spec(init_spec)
                    sys.modules[package_name] = init_module
                    init_spec.loader.exec_module(init_module)
                else:
                    ns_module = type(sys)(package_name)
                    ns_module.__path__ = [str(plugin_dir)]
                    ns_module.__package__ = package_name
                    ns_module.__name__ = package_name
                    sys.modules[package_name] = ns_module

            spec = importlib.util.spec_from_file_location(module_name, module_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            plugin_cls = None
            target_class_name = manifest.class_name
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase
                ):
                    if target_class_name:
                        if attr.__name__ == target_class_name:
                            plugin_cls = attr
                            break
                    else:
                        plugin_cls = attr
                        break

            if plugin_cls:
                cls._registry[manifest_id] = plugin_cls
                logger.info("  Registered plugin: %s (%s)", manifest_id, manifest.name)
                return manifest_id
            else:
                logger.warning("  No PluginBase subclass found in: %s", plugin_id)
                return None

        except Exception as e:
            logger.warning("  Failed to load plugin %s: %s", plugin_id, e)
            return None

    @classmethod
    def _scan_plugins(cls, plugins_dir: Path) -> None:
        key = str(plugins_dir.resolve())
        if key in cls._scanned_dirs:
            return

        if not plugins_dir.exists():
            logger.info("Plugins directory not found: %s (will be created on first run)", plugins_dir)
            cls._scanned_dirs.add(key)
            return

        logger.info("Scanning plugins from: %s", plugins_dir)

        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            cls._load_plugin_module(plugin_dir)

        cls._scanned_dirs.add(key)
        logger.info(
            "Plugin scan complete. Found %d plugin(s).", len(cls._registry)
        )

    @classmethod
    def _scan_single_plugin(cls, plugins_dir: Path, plugin_id: str) -> bool:
        """Scan a single plugin subdirectory and register it.

        Returns True on success, False on failure.
        """
        plugin_dir = plugins_dir / plugin_id
        if not plugin_dir.is_dir():
            return False
        return cls._load_plugin_module(plugin_dir) is not None

    @classmethod
    def _unregister_plugin(cls, plugin_id: str):
        """Remove plugin from class-level registries (for deletion and reinstall)."""
        cls._registry.pop(plugin_id, None)
        cls._manifests.pop(plugin_id, None)
        cls._schemas.pop(plugin_id, None)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load_plugin(self, plugin_id: str) -> bool:
        if plugin_id in self._plugins:
            logger.info("Plugin %s is already loaded", plugin_id)
            return True

        if plugin_id not in self._registry:
            logger.warning("Plugin %s not found in registry", plugin_id)
            return False

        runtime = self._runtime_configs.get(plugin_id)
        if runtime and not runtime.enabled:
            logger.info("Plugin %s is disabled in config, skipping", plugin_id)
            return False

        manifest = self._manifests[plugin_id]

        try:
            merged_config = _merge_config(manifest, self._schemas.get(plugin_id, []), runtime)
            plugin_cls = self._registry[plugin_id]
            plugin = plugin_cls(manifest, merged_config)

            self._wire_plugin(plugin, plugin_id)
            plugin.activate()

            self._plugins[plugin_id] = plugin
            logger.info("Plugin loaded: %s v%s", plugin_id, manifest.version)
            return True

        except Exception as e:
            logger.error("Failed to load plugin %s: %s", plugin_id, e, exc_info=True)
            self._unwire_plugin(plugin_id)
            return False

    def unload_plugin(self, plugin_id: str) -> bool:
        plugin = self._plugins.pop(plugin_id, None)
        if plugin is None:
            return True

        try:
            plugin.deactivate()
        except Exception as e:
            logger.warning("Plugin %s deactivate error: %s", plugin_id, e)
        finally:
            self._unwire_plugin(plugin_id)

        logger.info("Plugin unloaded: %s", plugin_id)
        return True

    def install_from_zip(self, zip_path: Path, target_dir: Path,
                         toolllm=None) -> dict:
        """Install plugin from zip. Unloads old version first on overwrite."""
        try:
            if not zipfile.is_zipfile(zip_path):
                return {"ok": False, "error": "不是有效的 zip 文件"}

            with zipfile.ZipFile(zip_path, 'r') as zf:
                names = zf.namelist()
                manifest_name = None
                for name in names:
                    if os.path.basename(name) == "manifest.json":
                        manifest_name = name
                        break
                if manifest_name is None:
                    return {"ok": False, "error": "插件包缺少 manifest.json"}

                for name in names:
                    norm = os.path.normpath(name)
                    if os.path.isabs(norm) or norm.split(os.sep, 1)[0] == '..':
                        return {"ok": False,
                                "error": f"不安全的文件路径: {name}"}

                manifest_data = json.loads(zf.read(manifest_name))
                plugin_id = manifest_data.get("id", "")
                if not plugin_id:
                    return {"ok": False, "error": "manifest.json 缺少 id 字段"}

            if plugin_id in self._registry:
                existing = self._manifests.get(plugin_id)
                if existing and existing.builtin:
                    return {"ok": False,
                            "error": f"与内置插件冲突: {plugin_id}"}
                logger.info("覆盖安装插件: %s (先卸载旧版本)", plugin_id)
                self.unload_plugin(plugin_id)
                self._unregister_plugin(plugin_id)

            extract_dir = target_dir / plugin_id
            if extract_dir.exists():
                shutil.rmtree(extract_dir)

            _safe_extract(zip_path, target_dir)

            if not self._scan_single_plugin(target_dir, plugin_id):
                shutil.rmtree(extract_dir, ignore_errors=True)
                return {"ok": False,
                        "error": "plugin.py 中没有合法的 PluginBase 子类"}

            ok = self.load_plugin(plugin_id)
            if not ok:
                return {"ok": False, "error": "插件注册成功但加载失败"}

            if toolllm:
                toolllm.rebuild_tool_definitions()

            return {"ok": True, "plugin_id": plugin_id}

        except (ValueError, zipfile.BadZipFile) as e:
            return {"ok": False, "error": str(e)}

    def load_all_enabled(self) -> Dict[str, bool]:
        results = {}
        for plugin_id in self._registry:
            runtime = self._runtime_configs.get(plugin_id)
            if runtime is None or runtime.enabled:
                results[plugin_id] = self.load_plugin(plugin_id)
        return results

    def unload_all(self) -> None:
        for plugin_id in reversed(list(self._plugins.keys())):
            self.unload_plugin(plugin_id)
        PluginManager._nav_items.clear()

    # ------------------------------------------------------------------
    # Extension point wiring
    # ------------------------------------------------------------------

    def _wire_plugin(self, plugin: PluginBase, plugin_id: str) -> None:
        registrations: Dict[str, list] = {}

        if isinstance(plugin, ToolProvider):
            registrations["tool"] = self._wire_tool(plugin, plugin_id)

        if isinstance(plugin, EventSubscriber):
            registrations["event"] = self._wire_event(plugin)

        if isinstance(plugin, WebUIProvider):
            registrations["webui"] = self._wire_webui(plugin, plugin_id)

        if isinstance(plugin, XMLTagHandler):
            registrations["xml_tag"] = self._wire_xml(plugin)

        if isinstance(plugin, PromptSectionProvider):
            self._pending_prompt_sections[plugin_id] = plugin.get_prompt_sections()

        self._hook_registrations[plugin_id] = registrations

    def _unwire_plugin(self, plugin_id: str) -> None:
        regs = self._hook_registrations.pop(plugin_id, {})

        for entry in regs.get("event", []):
            event_name, callback = entry
            from ..bus import bus
            bus.off(event_name, callback)

        for func_name in regs.get("tool", []):
            from ..function_caller import _unregister_plugin_handler
            _unregister_plugin_handler(func_name)
            from ..tools.registry import get_registry
            get_registry().unregister(func_name)

        for tag_name in regs.get("xml_tag", []):
            from ..parse_xml import _unregister_tag_handler
            _unregister_tag_handler(tag_name)

        for item in regs.get("webui", []):
            PluginManager._nav_items = [
                n for n in PluginManager._nav_items if n.get("id") != plugin_id
            ]

        self._pending_prompt_sections.pop(plugin_id, None)

    def _wire_prompt_sections(self, chatllm=None, toollLM=None, planllm=None) -> None:
        for plugin_id, sections in self._pending_prompt_sections.items():
            for agent_name, section in sections:
                try:
                    if agent_name == "chat" and chatllm and chatllm.context:
                        chatllm.context.add_section(section)
                        chatllm.refresh_context()
                    elif agent_name == "tool" and toollLM and toollLM.context:
                        toollLM.context.add_section(section)
                    elif agent_name == "plan" and planllm and planllm.context:
                        planllm.context.add_section(section)
                except Exception as e:
                    logger.warning(
                        "Failed to add prompt section from %s to %s: %s",
                        plugin_id, agent_name, e,
                    )

    # ---- Per-type wiring helpers ----

    @staticmethod
    def _wire_tool(plugin: ToolProvider, plugin_id: str) -> list:
        from functools import partial
        from ..function_caller import register_plugin_handler
        from ..tools.registry import get_registry

        registry = get_registry()
        registered = []
        for tool_def in plugin.get_tool_definitions():
            registry.register(tool_def)
            register_plugin_handler(tool_def.name, partial(plugin.execute_tool, tool_def.name))
            registered.append(tool_def.name)
            logger.info("  [%s] registered tool: %s", plugin_id, tool_def.name)
        return registered

    @staticmethod
    def _wire_event(plugin: EventSubscriber) -> list:
        from ..bus import bus

        subscriptions = plugin.get_event_subscriptions()
        registered = []
        for event_name, callback in subscriptions.items():
            bus.on(event_name, callback)
            registered.append((event_name, callback))
            logger.info("  subscribed to event: %s", event_name)
        return registered

    @staticmethod
    def _wire_webui(plugin: WebUIProvider, plugin_id: str) -> list:
        try:
            from webui.app import app

            blueprints = plugin.get_blueprints()
            for bp in blueprints:
                app.register_blueprint(bp)
        except Exception as e:
            logger.warning("  [%s] WebUI blueprint registration failed: %s", plugin_id, e)

        nav_items = plugin.get_nav_items()
        for item in nav_items:
            item.setdefault("id", plugin_id)
        PluginManager._nav_items.extend(nav_items)

        for item in nav_items:
            logger.info("  [%s] added nav item: %s -> %s", plugin_id, item.get("label"), item.get("href"))
        return nav_items

    @staticmethod
    def _wire_xml(plugin: XMLTagHandler) -> list:
        from ..parse_xml import _register_tag_handler

        tags = plugin.get_handled_tags()
        for tag_name in tags:
            _register_tag_handler(tag_name, plugin.handle_tag)
            logger.info("  registered XML tag handler: %s", tag_name)
        return tags

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @classmethod
    def list_available(cls) -> List[PluginManifest]:
        return list(cls._manifests.values())

    @classmethod
    def get_plugin_info(cls, plugin_id: str) -> Optional[dict]:
        manifest = cls._manifests.get(plugin_id)
        if manifest is None:
            return None
        return {
            "id": plugin_id,
            "manifest": {
                "name": manifest.name,
                "version": manifest.version,
                "author": manifest.author,
                "description": manifest.description,
                "hooks": manifest.hooks,
                "builtin": manifest.builtin,
            },
            "schema": cls._schemas.get(plugin_id, []),
        }

    def list_loaded(self) -> List[str]:
        return list(self._plugins.keys())

    def is_loaded(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins


def _merge_config(
    manifest: PluginManifest,
    schema: list,
    runtime: Optional[PluginRuntimeConfig],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for field in schema:
        if isinstance(field, dict) and "name" in field and "default" in field:
            merged[field["name"]] = field["default"]
    if runtime:
        merged.update(runtime.config)
    return merged


def _safe_extract(zip_path: Path, target_dir: Path) -> None:
    """Safe zip extraction — raises ValueError on path traversal or symlinks."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.namelist():
            member_path = os.path.normpath(member)
            if os.path.isabs(member_path) or member_path.split(os.sep, 1)[0] == '..':
                raise ValueError(f"不安全的路径: {member}")
            info = zf.getinfo(member)
            if hasattr(info, 'is_symlink'):
                is_symlink = info.is_symlink()
            else:
                is_symlink = (info.external_attr >> 16) & 0o120000 == 0o120000
            if is_symlink:
                raise ValueError(f"不允许符号链接: {member}")
        zf.extractall(target_dir)
