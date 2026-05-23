class PluginError(Exception):
    """Base exception for all plugin errors."""


class PluginLoadError(PluginError):
    """Failed to load a plugin module."""


class PluginActivateError(PluginError):
    """Failed to activate a plugin."""


class PluginDependencyError(PluginError):
    """Plugin has unmet dependencies."""
