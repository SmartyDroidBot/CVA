"""Plugin loader and discovery system"""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type
from .base import Plugin


class PluginLoader:
    """Loader for discovering and loading plugins"""
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._plugin_paths: List[Path] = []
    
    def add_plugin_path(self, path: Path):
        """
        Add a directory to search for plugins.
        
        Args:
            path: Directory path containing plugins
        """
        if path.exists() and path.is_dir():
            self._plugin_paths.append(path)
    
    def discover_plugins(self) -> List[str]:
        """
        Discover available plugins in plugin paths.
        
        Returns:
            List of discovered plugin module names
        """
        discovered = []
        
        for plugin_path in self._plugin_paths:
            # Look for Python files
            for py_file in plugin_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                
                module_name = py_file.stem
                discovered.append(module_name)
        
        return discovered
    
    def load_plugin_from_file(self, file_path: Path) -> Optional[Plugin]:
        """
        Load a plugin from a Python file.
        
        Args:
            file_path: Path to plugin Python file
            
        Returns:
            Plugin instance or None if loading failed
        """
        try:
            module_name = f"plugin_{file_path.stem}"
            
            # Load module from file
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                return None
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Look for Plugin class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, Plugin) and 
                    attr is not Plugin):
                    plugin = attr()
                    return plugin
            
            return None
            
        except Exception as e:
            print(f"Error loading plugin from {file_path}: {e}")
            return None
    
    def load_plugin(self, plugin_class: Type[Plugin], config: Optional[Dict] = None) -> bool:
        """
        Load and initialize a plugin.
        
        Args:
            plugin_class: Plugin class to load
            config: Plugin configuration
            
        Returns:
            True if loaded successfully
        """
        try:
            plugin = plugin_class()
            
            # Initialize plugin
            if plugin.initialize(config):
                self._plugins[plugin.name] = plugin
                return True
            else:
                print(f"Failed to initialize plugin: {plugin.name}")
                return False
                
        except Exception as e:
            print(f"Error loading plugin: {e}")
            return False
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """
        Get a loaded plugin by name.
        
        Args:
            name: Plugin name
            
        Returns:
            Plugin instance or None
        """
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[Plugin]:
        """
        List all loaded plugins.
        
        Returns:
            List of plugin instances
        """
        return list(self._plugins.values())
    
    def unload_plugin(self, name: str):
        """
        Unload a plugin.
        
        Args:
            name: Plugin name
        """
        if name in self._plugins:
            plugin = self._plugins[name]
            plugin.shutdown()
            del self._plugins[name]
    
    def unload_all(self):
        """Unload all plugins"""
        for plugin in list(self._plugins.values()):
            plugin.shutdown()
        self._plugins.clear()


# Global loader instance
_global_loader = PluginLoader()


def get_loader() -> PluginLoader:
    """Get the global plugin loader"""
    return _global_loader


def load_plugin(plugin_class: Type[Plugin], config: Optional[Dict] = None) -> bool:
    """Load a plugin in the global loader"""
    return _global_loader.load_plugin(plugin_class, config)


def get_plugin(name: str) -> Optional[Plugin]:
    """Get a plugin from the global loader"""
    return _global_loader.get_plugin(name)


def list_plugins() -> List[Plugin]:
    """List all loaded plugins"""
    return _global_loader.list_plugins()
