"""Lightweight MCP client wrapper built on langchain_mcp_adapters."""

from __future__ import annotations

from typing import Dict, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection


class MCPClient:
    """Minimal helper that instantiates MultiServerMCPClient and fetches tools."""

    def __init__(self, connections: Dict[str, Connection]):
        self._connections = connections
        self._client = MultiServerMCPClient(connections)
        self.tools = None

    async def get_tools(self, server_name: Optional[str] = None):
        """Fetch tools from configured MCP servers."""
        self.tools = await self._client.get_tools(server_name=server_name)
        return self.tools


__all__ = ["MCPClient"]
