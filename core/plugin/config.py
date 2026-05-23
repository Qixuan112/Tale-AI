from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class PluginRuntimeConfig:
    plugin_id: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, plugin_id: str, data: dict) -> "PluginRuntimeConfig":
        return cls(
            plugin_id=plugin_id,
            enabled=data.get("enabled", True),
            config=data.get("config", {}),
        )


def load_plugins_config(config_dir: Path) -> Dict[str, PluginRuntimeConfig]:
    """Load plugins.yaml and return {plugin_id: PluginRuntimeConfig}."""
    config_path = config_dir / "plugins.yaml"
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    plugins_data = raw.get("plugins", {})
    return {
        pid: PluginRuntimeConfig.from_dict(pid, cfg)
        for pid, cfg in plugins_data.items()
    }
