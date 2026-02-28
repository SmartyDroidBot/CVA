"""MCP Client — bridges multiple MCP servers to LangChain StructuredTools."""

import asyncio
import os
import sys
import yaml
from typing import List, Optional, Dict, Any, Tuple

from langchain_core.tools import StructuredTool
from pydantic import create_model

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import nest_asyncio

from src.ui import cli

# Allow nested event loops (needed for LangGraph sync → async bridge)
nest_asyncio.apply()


class McpClient:
    """Connects to a single MCP server and converts tools to LangChain format."""
    
    def __init__(self, name: str, config: dict):
        self.name = name
        self.command = config.get("command", "python")
        self.args = config.get("args", [])
        self.env_overrides = config.get("env", {})
        self._server_params = None
    
    def _get_server_params(self) -> StdioServerParameters:
        """Create server params for this specific MCP integration."""
        if self._server_params is None:
            env = os.environ.copy()
            # Ensure path is set (especially for npx)
            env["PATH"] = env.get("PATH", "")
            # Merge custom env vars (like MSF_PASSWORD)
            for k, v in self.env_overrides.items():
                env[k] = str(v)
            
            cmd = self.command
            if cmd == "python":
                cmd = sys.executable
            
            self._server_params = StdioServerParameters(
                command=cmd,
                args=self.args,
                env=env,
            )
        return self._server_params
    
    async def load_tools(self) -> Tuple[str, List[StructuredTool]]:
        """Connect to MCP server, discover tools, and wrap them."""
        params = self._get_server_params()
        tools = []
        
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    mcp_tools = await session.list_tools()
                    
                    for tool in mcp_tools.tools:
                        tools.append(self._convert_to_langchain(tool, params))
            return self.name, tools
        except Exception as e:
            cli.print_status(f"Error loading MCP server '{self.name}': {e}")
            return self.name, []
    
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
        try:
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
                        return f"Error from {self.name}: {output_text}"
                    return output_text
        except Exception as e:
            return f"Failed to execute {tool_name} on {self.name}: {e}"


async def _load_all_servers() -> List[StructuredTool]:
    """Parse config/mcp_servers.yaml and load all servers concurrently."""
    config_path = "config/mcp_servers.yaml"
    if not os.path.exists(config_path):
        cli.print_status("MCP config not found, loading defaults.", style="yellow")
        # Fallback to just the core server
        servers = {"cva_core": {"command": "python", "args": ["src/mcp_server/kali.py"]}}
    else:
        with open(config_path, "r") as f:
            yaml_content = yaml.safe_load(f)
            servers = yaml_content.get("mcp_servers", {})

    all_tools = []
    tasks = []
    
    for name, srv_config in servers.items():
        client = McpClient(name, srv_config)
        tasks.append(client.load_tools())
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for res in results:
        if isinstance(res, tuple):
            server_name, tools = res
            if tools:
                cli.print_status(f"Loaded MCP server: {server_name} ({len(tools)} tools)")
            all_tools.extend(tools)
        elif isinstance(res, Exception):
            cli.print_status(f"Unexpected error loading MCP server: {res}")

    return all_tools


def get_mcp_tools() -> List[StructuredTool]:
    """Synchronous entrypoint called by main.py."""
    return asyncio.run(_load_all_servers())
