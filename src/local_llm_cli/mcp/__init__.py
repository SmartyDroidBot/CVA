"""MCP integration helpers built on top of the minimal MCP client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.sessions import Connection

from .client import MCPClient

_connections: Dict[str, Connection] = {}
_client: Optional[MCPClient] = None
_tool_cache: List["RegisteredTool"] = []


@dataclass
class RegisteredTool:
    server_name: str
    tool: BaseTool

    @property
    def name(self) -> str:
        return getattr(self.tool, "name", "")

    @property
    def description(self) -> str:
        return getattr(self.tool, "description", "") or ""

    def get_parameters(self) -> List[Dict[str, Any]]:
        schema = getattr(self.tool, "args_schema", None)
        if schema is None:
            return []
        try:
            schema_dict = schema.model_json_schema()
        except Exception:  # noqa: BLE001
            return []
        properties = schema_dict.get("properties", {})
        required = set(schema_dict.get("required", []))
        return [
            {
                "name": name,
                "type": details.get("type", "string"),
                "description": details.get("description", ""),
                "required": name in required,
                "default": details.get("default"),
            }
            for name, details in properties.items()
        ]


def add_mcp_server(
    server_name: str,
    command: str,
    args: Optional[List[str]] = None,
    connection_type: str = "stdio",
    url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> bool:
    connection = _build_connection(
        command=command,
        args=args or [],
        connection_type=connection_type,
        url=url,
        headers=headers,
        env=env,
    )
    if connection is None:
        return False
    _connections[server_name] = connection
    _reset()
    return True


def get_mcp_tools() -> List[RegisteredTool]:
    if not _tool_cache:
        _refresh_tool_cache()
    return _tool_cache


def get_tool(tool_name: str) -> Optional[RegisteredTool]:
    for tool in get_mcp_tools():
        if tool.name == tool_name:
            return tool
    return None


def execute_tool(tool_name: str, **kwargs):
    tool = get_tool(tool_name)
    if not tool:
        return {"success": False, "output": None, "metadata": None, "error": f"Tool not found: {tool_name}"}

    try:
        result = _run_async(tool.tool.ainvoke(kwargs))
        output, metadata = _normalize_tool_output(result)
        return {"success": True, "output": output, "metadata": metadata, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "output": None, "metadata": None, "error": str(exc)}


def _refresh_tool_cache() -> None:
    _tool_cache.clear()
    if not _connections:
        return
    client = _ensure_client()
    for server_name in sorted(_connections.keys()):
        try:
            server_tools = _run_async(client.get_tools(server_name=server_name))
        except Exception as exc:  # noqa: BLE001
            print(f"Error retrieving tools from {server_name}: {exc}")
            continue
        for base_tool in server_tools:
            _tool_cache.append(RegisteredTool(server_name=server_name, tool=base_tool))


def _ensure_client() -> MCPClient:
    global _client
    if _client is None:
        _client = MCPClient(_connections.copy())
    return _client


def _reset() -> None:
    global _client
    _client = None
    _tool_cache.clear()


def _build_connection(
    *,
    command: str,
    args: List[str],
    connection_type: str,
    url: Optional[str],
    headers: Optional[Dict[str, str]],
    env: Optional[Dict[str, str]],
) -> Optional[Connection]:
    transport = connection_type.lower() if connection_type else ""
    if transport == "stdio":
        if not command:
            print("Stdio transport requires a command")
            return None
        connection: Connection = {
            "transport": "stdio",
            "command": command,
            "args": args,
        }
        if env is not None:
            connection["env"] = env
        return connection

    if transport in {"sse", "streamable_http", "streamable-http", "websocket"}:
        if not url:
            print(f"Transport '{connection_type}' requires a URL")
            return None
        normalized_transport = "streamable_http" if transport == "streamable-http" else transport
        connection: Connection = {"transport": normalized_transport, "url": url}
        if headers:
            connection["headers"] = headers
        return connection

    print(f"Unsupported MCP transport '{connection_type}' for server configuration")
    return None


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        try:
            asyncio.set_event_loop(None)
        except RuntimeError:
            pass


def _normalize_tool_output(raw_output: Any) -> tuple[str, Optional[Dict[str, Any]]]:
    metadata: Optional[Dict[str, Any]] = None
    text_output: str

    if isinstance(raw_output, tuple) and len(raw_output) == 2:
        text_part, artifacts = raw_output
        text_output = _stringify_text(text_part)
        if artifacts:
            metadata = {"artifacts": artifacts}
    else:
        text_output = _stringify_text(raw_output)

    return text_output, metadata


def _stringify_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


__all__ = [
    "RegisteredTool",
    "add_mcp_server",
    "get_mcp_tools",
    "get_tool",
    "execute_tool",
]
