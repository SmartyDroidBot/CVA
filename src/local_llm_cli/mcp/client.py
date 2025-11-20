"""MCP (Model Context Protocol) client for tool integration"""

import asyncio
from asyncio.subprocess import DEVNULL, Process
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from httpx import HTTPStatusError
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client


@dataclass
class MCPTool:
    """Represents a tool from an MCP server"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    
    def get_parameters(self) -> List[Dict[str, Any]]:
        """Extract parameters from input schema"""
        schema = self.input_schema
        if "properties" not in schema:
            return []
        
        parameters = []
        required = schema.get("required", [])
        
        for param_name, param_info in schema["properties"].items():
            parameters.append({
                "name": param_name,
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
                "required": param_name in required,
                "default": param_info.get("default")
            })
        
        return parameters


class MCPToolWrapper:
    """Wrapper to handle MCP tool execution"""
    
    def __init__(self, tool: MCPTool, server_connection: 'MCPServerConnection'):
        self.tool = tool
        self._server = server_connection
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the MCP tool synchronously"""
        # Create a new event loop for this execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._execute_async(**kwargs))
            return result
        finally:
            loop.close()
    
    async def _execute_async(self, **kwargs) -> Dict[str, Any]:
        """Execute the MCP tool asynchronously"""
        try:
            result = await self._server.call_tool(self.tool.name, kwargs)
            return {
                "success": True,
                "output": result,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e)
            }


class MCPServerConnection:
    """Manages connection to a single MCP server"""
    
    def __init__(self, server_name: str, command: str, args: List[str], connection_type: str = "stdio", url: Optional[str] = None, headers: Optional[Dict[str, str]] = None):
        self.server_name = server_name
        self.command = command
        self.args = args
        self.connection_type = connection_type
        self.url = url
        self.headers = headers or {}
        self._session: Optional[ClientSession] = None
        self._read = None
        self._write = None
        self._initialized = False
        self._context_manager = None
        self._process: Optional[Process] = None
    
    async def connect(self):
        """Connect to the MCP server"""
        if self._initialized:
            return
        
        try:
            if self.connection_type == "sse":
                # SSE connection
                if not self.url:
                    print(f"Error: SSE connection requires URL for server {self.server_name}")
                    self._initialized = False
                    return

                if self.command:
                    launched = await self._launch_sse_process()
                    if not launched:
                        self._initialized = False
                        return
                
                # Create SSE client with headers
                sse_ctx = sse_client(self.url, headers=self.headers if self.headers else None)
                
                try:
                    self._read, self._write = await asyncio.wait_for(
                        sse_ctx.__aenter__(),
                        timeout=10.0
                    )
                    self._context_manager = sse_ctx
                except asyncio.TimeoutError:
                    print(f"Timeout connecting to SSE MCP server {self.server_name} at {self.url}")
                    self._initialized = False
                    await self._shutdown_process()
                    return
                except HTTPStatusError as exc:
                    status = exc.response.status_code if exc.response else "unknown"
                    self._print_http_error(status)
                    self._initialized = False
                    await self._shutdown_process()
                    return
                except Exception as e:
                    status = self._find_http_status(e)
                    if status is not None:
                        self._print_http_error(status)
                    else:
                        print(f"Error connecting to SSE server {self.server_name}: {e}")
                    self._initialized = False
                    await self._shutdown_process()
                    return
            else:
                # Stdio connection
                server_params = StdioServerParameters(
                    command=self.command,
                    args=self.args,
                    env=None
                )
                
                # Create stdio client using context manager with timeout
                stdio_ctx = stdio_client(server_params)
                
                # Use asyncio.wait_for with timeout
                try:
                    self._read, self._write = await asyncio.wait_for(
                        stdio_ctx.__aenter__(),
                        timeout=5.0
                    )
                    self._context_manager = stdio_ctx
                except asyncio.TimeoutError:
                    print(f"Timeout connecting to stdio MCP server {self.server_name}")
                    self._initialized = False
                    return
            
            # Create session
            self._session = ClientSession(self._read, self._write)
            
            # Initialize the session with timeout
            try:
                await asyncio.wait_for(self._session.initialize(), timeout=30.0)
            except asyncio.TimeoutError:
                print(f"Timeout initializing MCP server {self.server_name} (waited 30s)")
                self._initialized = False
                return
            except Exception as e:
                print(f"Error during initialization of {self.server_name}: {e}")
                import traceback
                traceback.print_exc()
                self._initialized = False
                return
            
            self._initialized = True
            
        except Exception as e:
            print(f"Error connecting to MCP server {self.server_name}: {e}")
            self._initialized = False
    
    async def disconnect(self):
        """Disconnect from the MCP server"""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None
        
        # Clean up stdio streams
        if self._write:
            try:
                self._write.close()
            except Exception:
                pass
        
        await self._shutdown_process()
        self._initialized = False

    async def _launch_sse_process(self) -> bool:
        """Launch a local SSE proxy/server if a command is provided."""
        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdout=DEVNULL,
                stderr=DEVNULL,
            )
            await asyncio.sleep(1.0)
            return True
        except FileNotFoundError:
            print(
                f"Error: Unable to launch SSE server '{self.server_name}'. Command not found: {self.command}"
            )
            return False
        except Exception as exc:
            print(
                f"Error launching SSE server '{self.server_name}' via command '{self.command}': {exc}"
            )
            return False

    async def _shutdown_process(self):
        """Best-effort shutdown for launched SSE processes."""
        if not self._process:
            return
        try:
            if self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
        finally:
            self._process = None

    def _find_http_status(self, exc: BaseException) -> Optional[int]:
        """Walk nested ExceptionGroups to find an HTTP status error code."""
        if isinstance(exc, HTTPStatusError):
            return exc.response.status_code if exc.response else None

        nested = getattr(exc, "exceptions", None)
        if not nested:
            return None

        for inner in nested:
            status = self._find_http_status(inner)
            if status is not None:
                return status
        return None

    def _print_http_error(self, status: int | str):
        print(
            f"Error connecting to SSE server {self.server_name}: HTTP {status} from {self.url}."
        )
        print("Ensure the MCP proxy/server is running or disable it in your config.")
    
    async def list_tools(self) -> List[MCPTool]:
        """List all available tools from this server"""
        if not self._session:
            return []
        
        try:
            tools_list = await self._session.list_tools()
            return [
                MCPTool(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    server_name=self.server_name
                )
                for tool in tools_list.tools
            ]
        except Exception as e:
            print(f"Error listing tools from {self.server_name}: {e}")
            return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on this server"""
        if not self._session:
            raise RuntimeError(f"Not connected to server {self.server_name}")
        
        try:
            result = await self._session.call_tool(tool_name, arguments)
            
            # Extract text content from result
            if hasattr(result, 'content'):
                content_parts = []
                for content in result.content:
                    if hasattr(content, 'text'):
                        content_parts.append(content.text)
                return "\n".join(content_parts)
            
            return str(result)
            
        except Exception as e:
            raise RuntimeError(f"Error calling tool {tool_name}: {e}")


class MCPManager:
    """Manages multiple MCP server connections"""
    
    def __init__(self):
        self._servers: Dict[str, MCPServerConnection] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def add_server(self, server_name: str, command: str, args: List[str], connection_type: str = "stdio", url: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> bool:
        """Add an MCP server connection"""
        if server_name in self._servers:
            print(f"Server {server_name} already exists")
            return False
        
        connection = MCPServerConnection(server_name, command, args, connection_type, url, headers)
        
        # Connect to the server
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(connection.connect())
            if connection._initialized:
                self._servers[server_name] = connection
                return True
            return False
        finally:
            loop.close()
    
    def remove_server(self, server_name: str) -> bool:
        """Remove an MCP server connection"""
        if server_name not in self._servers:
            return False
        
        connection = self._servers[server_name]
        
        # Disconnect from the server
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(connection.disconnect())
        finally:
            loop.close()
        
        del self._servers[server_name]
        return True
    
    def get_all_tools(self) -> List[MCPTool]:
        """Get all tools from all connected servers (synchronous)"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._get_all_tools_async())
        finally:
            loop.close()
    
    async def _get_all_tools_async(self) -> List[MCPTool]:
        """Get all tools from all connected servers (asynchronous)"""
        all_tools = []
        for server in self._servers.values():
            tools = await server.list_tools()
            all_tools.extend(tools)
        return all_tools
    
    def get_tool(self, tool_name: str) -> Optional[MCPToolWrapper]:
        """Get a tool wrapper by name"""
        tools = self.get_all_tools()
        for tool in tools:
            if tool.name == tool_name:
                # Find the server connection for this tool
                server = self._servers.get(tool.server_name)
                if server:
                    return MCPToolWrapper(tool, server)
        return None
    
    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name"""
        tool_wrapper = self.get_tool(tool_name)
        if not tool_wrapper:
            return {
                "success": False,
                "output": None,
                "error": f"Tool not found: {tool_name}"
            }
        return tool_wrapper.execute(**kwargs)
    
    def list_servers(self) -> List[str]:
        """List all connected server names"""
        return list(self._servers.keys())
    
    def __del__(self):
        """Cleanup on deletion"""
        # Disconnect all servers
        for server_name in list(self._servers.keys()):
            self.remove_server(server_name)
