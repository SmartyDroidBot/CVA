"""Plugin system for extending functionality"""

from .base import Plugin
from .loader import (
    PluginLoader,
    get_loader,
    load_plugin,
    get_plugin,
    list_plugins,
)

__all__ = [
    "Plugin",
    "PluginLoader",
    "get_loader",
    "load_plugin",
    "get_plugin",
    "list_plugins",
]
