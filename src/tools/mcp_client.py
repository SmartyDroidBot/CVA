"""MCP Client — bridges MCP server tools to LangChain StructuredTool."""

import asyncio
import os
import sys
from typing import List, Optional, Dict, Any

from langchain_core.tools import StructuredTool
from pydantic import create_model

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import nest_asyncio

# Allow nested event loops (needed for LangGraph sync → async bridge)
nest_asyncio.apply()


class McpClient:
    """Connects to MCP servers and converts tools to LangChain format."""
    
    def __init__(self, server_script: str = "src/mcp_server/kali.py"):
        self.server_script = server_script
        self._server_params = None
    
    def _get_server_params(self) -> StdioServerParameters:
        """Create server params using the current Python interpreter."""
        if self._server_params is None:
            env = os.environ.copy()
            env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
            self._server_params = StdioServerParameters(
                command=sys.executable,
                args=[self.server_script],
                env=env,
            )
        return self._server_params
    
    async def load_tools(self) -> List[StructuredTool]:
        """Connect to MCP server, discover tools, and wrap them as LangChain tools."""
        params = self._get_server_params()
        tools = []
        
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                mcp_tools = await session.list_tools()
                
                for tool in mcp_tools.tools:
                    tools.append(self._convert_to_langchain(tool, params))
        
        return tools
    
    def _convert_to_langchain(self, tool_info: Any, server_params: StdioServerParameters) -> StructuredTool:
        """Convert an MCP tool definition to a LangChain StructuredTool."""
        tool_name = tool_info.name
        tool_desc = tool_info.description or "No description."
        
        # Build Pydantic model from JSON Schema
        input_schema = tool_info.inputSchema
        fields = {}
        
        if "properties" in input_schema:
            required = input_schema.get("required", [])
            for prop_name, prop_def in input_schema["properties"].items():
                p_type = str
                json_type = prop_def.get("type", "string")
                if json_type == "integer":
                    p_type = int
                elif json_type == "boolean":
                    p_type = bool
                elif json_type == "number":
                    p_type = float
                
                if prop_name in required:
                    fields[prop_name] = (p_type, ...)
                else:
                    fields[prop_name] = (Optional[p_type], None)
        
        args_model = create_model(f"{tool_name}Input", **fields)
        
        # Closure to execute tool via fresh MCP connection
        def run_tool(**kwargs):
            return asyncio.run(self._execute_mcp_tool(server_params, tool_name, kwargs))
        
        return StructuredTool.from_function(
            func=run_tool,
            name=tool_name,
            description=tool_desc,
            args_schema=args_model,
        )
    
    async def _execute_mcp_tool(self, server_params: StdioServerParameters, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a single tool call via a fresh MCP connection."""
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                
                output_text = ""
                if result.content:
                    for content in result.content:
                        if content.type == "text":
                            output_text += content.text
                
                if result.isError:
                    return f"Error: {output_text}"
                return output_text


def get_mcp_tools() -> List[StructuredTool]:
    """Synchronous helper to load all MCP tools."""
    client = McpClient()
    return asyncio.run(client.load_tools())
