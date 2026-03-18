"""MCP Client — bridges multiple MCP servers to LangChain StructuredTools.

Uses persistent subprocess connections that stay alive across tool invocations.
"""

import asyncio
import atexit
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

# Shared event loop for all MCP operations
_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """Get or create the shared event loop for MCP operations."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _run_async(coro):
    """Run an async coroutine in the shared event loop."""
    loop = _get_loop()
    return loop.run_until_complete(coro)


class McpClient:
    """Connects to a single MCP server and keeps a persistent connection."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.command = config.get("command", "python")
        self.args = config.get("args", [])
        self.env_overrides = config.get("env", {})
        self.enabled = config.get("enabled", True)
        self._server_params = None
        # Persistent connection state
        self._session: Optional[ClientSession] = None
        self._cm_stack = None  # context manager stack for cleanup

    def _get_server_params(self) -> StdioServerParameters:
        """Create server params for this specific MCP integration."""
        if self._server_params is None:
            env = os.environ.copy()
            env["PATH"] = env.get("PATH", "")
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

    async def connect_and_load(self) -> Tuple[str, List[StructuredTool]]:
        """Connect to MCP server, discover tools, and wrap them.

        The connection is kept alive for future tool calls.
        """
        if not self.enabled:
            return self.name, []

        params = self._get_server_params()
        tools = []

        try:
            # We need to keep the context managers alive, so we use
            # contextlib.AsyncExitStack-style manual management
            from contextlib import AsyncExitStack
            self._cm_stack = AsyncExitStack()
            read, write = await self._cm_stack.enter_async_context(
                stdio_client(params)
            )
            self._session = await self._cm_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            mcp_tools = await self._session.list_tools()

            for tool in mcp_tools.tools:
                tools.append(self._convert_to_langchain(tool))
            return self.name, tools
        except Exception as e:
            cli.print_status(f"Error loading MCP server '{self.name}': {e}", style="bold red")
            await self._cleanup()
            return self.name, []

    def _convert_to_langchain(self, tool_info: Any) -> StructuredTool:
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

        # Closure to execute tool via persistent connection, with reconnect fallback
        client_ref = self

        def run_tool(**kwargs):
            return _run_async(client_ref._execute_tool(tool_name, kwargs))

        return StructuredTool.from_function(
            func=run_tool,
            name=tool_name,
            description=tool_desc,
            args_schema=args_model,
        )

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a single tool call via the persistent session.

        Falls back to a fresh connection if the persistent session is dead.
        """
        # Try persistent session first
        if self._session is not None:
            try:
                result = await self._session.call_tool(tool_name, args)
                return self._format_result(result)
            except Exception:
                # Session died — try fresh connection
                await self._cleanup()

        # Fallback: one-shot connection
        try:
            params = self._get_server_params()
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, args)
                    return self._format_result(result)
        except Exception as e:
            return f"Failed to execute {tool_name} on {self.name}: {e}"

    def _format_result(self, result) -> str:
        """Format an MCP tool result into a string."""
        output_text = ""
        if result.content:
            for content in result.content:
                if content.type == "text":
                    output_text += content.text
        if result.isError:
            return f"Error from {self.name}: {output_text}"
        return output_text

    async def _cleanup(self):
        """Close the persistent connection."""
        if self._cm_stack is not None:
            try:
                await self._cm_stack.aclose()
            except Exception:
                pass
            self._cm_stack = None
            self._session = None


# ── Module-level registry ────────────────────────────────────────────────────

_clients: List[McpClient] = []


async def _load_all_servers() -> List[StructuredTool]:
    """Parse config/mcp_servers.yaml and load all servers concurrently."""
    global _clients

    config_path = "config/mcp_servers.yaml"
    if not os.path.exists(config_path):
        cli.print_status("MCP config not found, loading defaults.", style="yellow")
        servers = {"cva_core": {"command": "python", "args": ["src/mcp_server/kali.py"]}}
    else:
        with open(config_path, "r") as f:
            yaml_content = yaml.safe_load(f)
            servers = yaml_content.get("mcp_servers", {})

    all_tools = []
    tasks = []

    for name, srv_config in servers.items():
        client = McpClient(name, srv_config)
        _clients.append(client)
        tasks.append(client.connect_and_load())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, tuple):
            server_name, tools = res
            if tools:
                cli.print_status(f"Loaded MCP server: {server_name} ({len(tools)} tools)")
            all_tools.extend(tools)
        elif isinstance(res, Exception):
            cli.print_status(f"Unexpected error loading MCP server: {res}", style="bold red")

    return all_tools


async def _shutdown_all():
    """Cleanly shutdown all persistent MCP connections."""
    for client in _clients:
        await client._cleanup()
    _clients.clear()


def shutdown_mcp():
    """Synchronous entrypoint to shut down all MCP connections."""
    try:
        _run_async(_shutdown_all())
    except Exception:
        pass


def get_mcp_tools() -> List[StructuredTool]:
    """Synchronous entrypoint called by main.py."""
    tools = _run_async(_load_all_servers())
    atexit.register(shutdown_mcp)
    return tools
