"""
Template for creating plugins

Plugins can provide custom tools, agents, backends, and other functionality.
Copy this file to create your own plugin.

Place plugins in a custom plugins directory and load them at runtime.
"""

from typing import List, Optional, Dict, Any
from cva_cli.plugins import Plugin
from cva_cli.tools import Tool, register_tool
from cva_cli.agents import AgentConfig, register_config


class ExamplePlugin(Plugin):
    """Example plugin demonstrating the plugin interface"""
    
    def get_name(self) -> str:
        """Unique name for this plugin"""
        return "example_plugin"
    
    def get_version(self) -> str:
        """Plugin version (semantic versioning recommended)"""
        return "1.0.0"
    
    def get_description(self) -> str:
        """Brief description of what this plugin provides"""
        return "Example plugin providing custom tools and agents"
    
    def get_dependencies(self) -> List[str]:
        """
        List of required Python packages.
        
        Returns:
            List of package names (e.g., ["requests", "beautifulsoup4"])
        """
        return []  # Add dependencies like ["requests>=2.0.0"]
    
    def get_config_schema(self) -> Optional[Dict[str, Any]]:
        """
        Configuration schema for this plugin.
        
        Returns:
            Dictionary defining configuration options
        """
        return {
            "api_key": {
                "type": "string",
                "description": "API key for external service",
                "required": False,
                "default": None,
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds",
                "required": False,
                "default": 30,
            }
        }
    
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize the plugin.
        
        This is where you:
        - Register custom tools
        - Register custom agents
        - Set up resources
        - Validate configuration
        
        Args:
            config: Plugin configuration
            
        Returns:
            True if initialization successful
        """
        try:
            # Store config
            self.config = config or {}
            
            # Register custom tools
            # tool = MyCustomTool()
            # register_tool(tool)
            
            # Register custom agents
            # agent_config = AgentConfig(...)
            # register_config(agent_config)
            
            print(f"Plugin '{self.name}' initialized successfully")
            return True
            
        except Exception as e:
            print(f"Failed to initialize plugin '{self.name}': {e}")
            return False
    
    def shutdown(self):
        """
        Cleanup when plugin is unloaded.
        
        This is where you:
        - Close connections
        - Release resources
        - Save state
        """
        print(f"Plugin '{self.name}' shutting down")
    
    def get_provided_tools(self) -> List[str]:
        """
        List of tool names this plugin provides.
        
        Returns:
            List of tool names
        """
        return []  # e.g., ["web_search", "image_generator"]
    
    def get_provided_agents(self) -> List[str]:
        """
        List of agent names this plugin provides.
        
        Returns:
            List of agent names
        """
        return []  # e.g., ["web_researcher", "image_artist"]


# Example: More complex plugin with tools and agents
class WebScraperPlugin(Plugin):
    """Example plugin that adds web scraping capabilities"""
    
    def get_name(self) -> str:
        return "web_scraper"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def get_description(self) -> str:
        return "Adds web scraping and search capabilities"
    
    def get_dependencies(self) -> List[str]:
        return ["requests", "beautifulsoup4"]
    
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        try:
            # Check dependencies
            import requests
            from bs4 import BeautifulSoup
            
            # Would register custom tools here
            # from .tools import WebScraperTool, WebSearchTool
            # register_tool(WebScraperTool())
            # register_tool(WebSearchTool())
            
            # Would register custom agent
            # from .agents import WEB_RESEARCHER_AGENT
            # register_config(WEB_RESEARCHER_AGENT)
            
            return True
            
        except ImportError as e:
            print(f"Missing dependency: {e}")
            return False
    
    def get_provided_tools(self) -> List[str]:
        return ["web_scraper", "web_search"]
    
    def get_provided_agents(self) -> List[str]:
        return ["web_researcher"]


# To use this plugin:
# 
# 1. Save to a plugins directory
# 2. Load in your code:
#    from cva_cli.plugins import load_plugin
#    plugin = ExamplePlugin()
#    load_plugin(plugin.__class__, config={"api_key": "..."})
# 
# 3. Or load from file:
#    from cva_cli.plugins import get_loader
#    loader = get_loader()
#    loader.add_plugin_path(Path("./plugins"))
#    plugins = loader.discover_plugins()
