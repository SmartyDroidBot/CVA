"""MCP integration for tool support"""

from .client import MCPManager, MCPServerConnection, MCPTool, MCPToolWrapper

# Global MCP manager instance
_mcp_manager = None


def get_mcp_manager() -> MCPManager:
    """Get the global MCP manager instance"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


def add_mcp_server(server_name: str, command: str, args: list = None, connection_type: str = "stdio", url: str = None, headers: dict = None) -> bool:
    """Add an MCP server to the global manager"""
    manager = get_mcp_manager()
    return manager.add_server(server_name, command, args or [], connection_type, url, headers)


def get_mcp_tools() -> list:
    """Get all tools from connected MCP servers"""
    manager = get_mcp_manager()
    return manager.get_all_tools()


def get_tool(tool_name: str):
    """Get a tool wrapper by name"""
    manager = get_mcp_manager()
    return manager.get_tool(tool_name)


def execute_tool(tool_name: str, **kwargs):
    """Execute a tool by name"""
    manager = get_mcp_manager()
    return manager.execute_tool(tool_name, **kwargs)


__all__ = [
    "MCPManager",
    "MCPServerConnection", 
    "MCPTool",
    "MCPToolWrapper",
    "get_mcp_manager",
    "add_mcp_server",
    "get_mcp_tools",
    "get_tool",
    "execute_tool",
]
