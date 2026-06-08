"""Plugin config persistence helpers. Atomic write to prevent file corruption."""
import os
import threading

import yaml

_write_lock = threading.Lock()


def save_plugin_config(data_dir: str, plugin_id: str, enabled: bool,
                       extra_config: dict | None = None) -> None:
    """Save a plugin's enabled state and config to plugins.yaml."""
    config_path = os.path.join(data_dir, "config", "plugins.yaml")
    with _write_lock:
        data = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        data.setdefault("plugins", {})[plugin_id] = {
            "enabled": enabled,
            "config": extra_config or {},
        }
        tmp_path = config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)
        os.replace(tmp_path, config_path)


def remove_plugin_config(data_dir: str, plugin_id: str) -> None:
    """Remove a plugin's config entry from plugins.yaml."""
    config_path = os.path.join(data_dir, "config", "plugins.yaml")
    with _write_lock:
        data = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        data.get("plugins", {}).pop(plugin_id, None)
        tmp_path = config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)
        os.replace(tmp_path, config_path)
