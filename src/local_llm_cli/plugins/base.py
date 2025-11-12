"""Base plugin interface"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class Plugin(ABC):
    """Base class for plugins"""
    
    def __init__(self):
        self.name = self.get_name()
        self.version = self.get_version()
        self.description = self.get_description()
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the plugin name"""
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        """Return the plugin version"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Return a brief description of the plugin"""
        pass
    
    def get_dependencies(self) -> List[str]:
        """
        Return list of required dependencies.
        
        Returns:
            List of dependency names (e.g., ["requests", "beautifulsoup4"])
        """
        return []
    
    def get_config_schema(self) -> Optional[Dict[str, Any]]:
        """
        Return configuration schema for the plugin.
        
        Returns:
            Dictionary defining configuration options
        """
        return None
    
    @abstractmethod
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize the plugin.
        
        Args:
            config: Plugin configuration
            
        Returns:
            True if initialization successful
        """
        pass
    
    def shutdown(self):
        """
        Cleanup when plugin is unloaded.
        Override if needed.
        """
        pass
    
    def get_provided_tools(self) -> List[str]:
        """
        Return list of tool names this plugin provides.
        
        Returns:
            List of tool class names or instances
        """
        return []
    
    def get_provided_agents(self) -> List[str]:
        """
        Return list of agent names this plugin provides.
        
        Returns:
            List of agent config names
        """
        return []
    
    def __repr__(self) -> str:
        return f"Plugin(name='{self.name}', version='{self.version}')"
