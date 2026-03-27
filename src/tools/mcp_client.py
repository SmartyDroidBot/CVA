"""MCP Client — bridges multiple MCP servers to LangChain StructuredTools.

Uses a dedicated background thread with its own event loop for all async MCP
operations, avoiding nest_asyncio conflicts with Python 3.13.
"""

import asyncio
import atexit
import os
import sys
import threading
import yaml
from contextlib import AsyncExitStack
from typing import List, Optional, Dict, Any, Tuple

from langchain_core.tools import StructuredTool
from pydantic import create_model

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.ui import cli


# ── Dedicated event loop thread ───────────────────────────────────────────────
# All async MCP operations run in this single background thread to avoid
# asyncio context conflicts in Python 3.13.

_LOOP: Optional[asyncio.AbstractEventLoop] = None
_LOOP_THREAD: Optional[threading.Thread] = None
_LOOP_LOCK = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """Get (or create) the dedicated background event loop."""
    global _LOOP, _LOOP_THREAD
    with _LOOP_LOCK:
        if _LOOP is None or _LOOP.is_closed():
            _LOOP = asyncio.new_event_loop()
            _LOOP_THREAD = threading.Thread(
                target=_LOOP.run_forever, daemon=True, name="cva-mcp-loop"
            )
            _LOOP_THREAD.start()
        return _LOOP


def _run_async(coro, timeout: float = 120.0):
    """Submit a coroutine to the background event loop and block until done."""
    loop = _get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ── MCP Client ────────────────────────────────────────────────────────────────

class McpClient:
    """Connects to a single MCP server and keeps a persistent connection."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.command = config.get("command", "python")
        self.args = config.get("args", [])
        self.env_overrides = config.get("env", {})
        self.enabled = config.get("enabled", True)
        self._server_params: Optional[StdioServerParameters] = None
        self._session: Optional[ClientSession] = None
        self._cm_stack: Optional[AsyncExitStack] = None

    def _get_server_params(self) -> StdioServerParameters:
        if self._server_params is None:
            env = os.environ.copy()
            for k, v in self.env_overrides.items():
                env[k] = str(v)
            cmd = sys.executable if self.command == "python" else self.command
            self._server_params = StdioServerParameters(
                command=cmd, args=self.args, env=env
            )
        return self._server_params

    async def _connect_and_load(self) -> Tuple[str, List[StructuredTool]]:
        """Async: connect, discover tools, keep connection alive."""
        if not self.enabled:
            return self.name, []

        try:
            self._cm_stack = AsyncExitStack()
            read, write = await self._cm_stack.enter_async_context(
                stdio_client(self._get_server_params())
            )
            self._session = await self._cm_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            mcp_tools = await self._session.list_tools()

            tools = [self._to_langchain(t) for t in mcp_tools.tools]
            return self.name, tools
        except Exception as e:
            cli.print_status(f"MCP server '{self.name}' failed: {e}", style="bold red")
            await self._cleanup()
            return self.name, []

    def connect_and_load(self) -> Tuple[str, List[StructuredTool]]:
        """Synchronous wrapper — blocks until server is connected."""
        return _run_async(self._connect_and_load(), timeout=30.0)

    def _to_langchain(self, tool_info: Any) -> StructuredTool:
        """Convert an MCP tool to a LangChain StructuredTool."""
        name = tool_info.name
        desc = tool_info.description or "No description."
        schema = tool_info.inputSchema
        fields: dict = {}

        if "properties" in schema:
            required = schema.get("required", [])
            for prop, defn in schema["properties"].items():
                jtype = defn.get("type", "string")
                ptype = {
                    "string": str, "integer": int, "number": float,
                    "boolean": bool, "array": list, "object": dict,
                }.get(jtype, str)
                fields[prop] = (ptype, ...) if prop in required else (Optional[ptype], None)

        model = create_model(f"{name}Input", **fields)
        client_ref = self

        def run_tool(**kwargs):
            return _run_async(client_ref._execute_tool(name, kwargs))

        return StructuredTool.from_function(
            func=run_tool, name=name, description=desc, args_schema=model
        )

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool via the persistent session, reconnecting if needed."""
        if self._session is not None:
            try:
                result = await self._session.call_tool(tool_name, args)
                return self._format(result)
            except Exception:
                await self._cleanup()

        # Fallback: one-shot connection
        try:
            async with stdio_client(self._get_server_params()) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, args)
                    return self._format(result)
        except Exception as e:
            return f"Tool execution failed [{self.name}/{tool_name}]: {e}"

    def _format(self, result) -> str:
        parts = []
        if result.content:
            for c in result.content:
                if c.type == "text":
                    parts.append(c.text)
        output = "\n".join(parts)
        return f"Error: {output}" if result.isError else output

    async def _cleanup(self):
        if self._cm_stack:
            try:
                await self._cm_stack.aclose()
            except Exception:
                pass
        self._cm_stack = None
        self._session = None


# ── Module-level registry ─────────────────────────────────────────────────────

_clients: List[McpClient] = []


def get_mcp_tools() -> List[StructuredTool]:
    """Load all enabled MCP servers and return their tools as LangChain tools."""
    global _clients

    config_path = "config/mcp_servers.yaml"
    if not os.path.exists(config_path):
        servers = {"cva_core": {"command": "python", "args": ["src/mcp_server/kali.py"], "enabled": True}}
    else:
        with open(config_path, "r") as f:
            servers = yaml.safe_load(f).get("mcp_servers", {})

    all_tools: List[StructuredTool] = []
    for name, config in servers.items():
        if not config.get("enabled", True):
            continue
        client = McpClient(name, config)
        _clients.append(client)
        try:
            server_name, tools = client.connect_and_load()
            if tools:
                cli.print_status(f"Loaded MCP server: {server_name} ({len(tools)} tools)")
            all_tools.extend(tools)
        except Exception as e:
            cli.print_status(f"Failed to load '{name}': {e}", style="bold red")

    atexit.register(shutdown_mcp)
    return all_tools


def shutdown_mcp():
    """Cleanly shut down all MCP connections."""
    loop = _get_loop()
    async def _close_all():
        for c in _clients:
            await c._cleanup()
        _clients.clear()
    try:
        asyncio.run_coroutine_threadsafe(_close_all(), loop).result(timeout=5.0)
    except Exception:
        pass
