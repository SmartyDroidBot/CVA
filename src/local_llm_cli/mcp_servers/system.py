"""Built-in MCP server providing system information and command tools"""

import asyncio
import platform
import sys
import subprocess
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Create server instance
app = Server("builtin-system")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available system tools"""
    return [
        Tool(
            name="system_info",
            description="Get information about the system",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="shell_command",
            description="Execute a shell command (use with caution)",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                        "default": 30
                    }
                },
                "required": ["command"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "system_info":
        return await system_info(arguments)
    elif name == "shell_command":
        return await shell_command(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def system_info(arguments: dict) -> list[TextContent]:
    """Get system information"""
    try:
        info = {
            "Platform": platform.system(),
            "Release": platform.release(),
            "Version": platform.version(),
            "Architecture": platform.machine(),
            "Processor": platform.processor(),
            "Python Version": sys.version.split()[0],
            "Python Implementation": platform.python_implementation(),
        }
        
        result = "System Information:\n\n"
        for key, value in info.items():
            result += f"  {key}: {value}\n"
        
        return [TextContent(type="text", text=result)]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error getting system info: {str(e)}"
        )]


async def shell_command(arguments: dict) -> list[TextContent]:
    """Execute shell command"""
    command = arguments.get("command", "")
    timeout = arguments.get("timeout", 30)
    
    # Security: List of blocked commands
    blocked_keywords = ["rm -rf", "del /f", "format", "mkfs", "dd if="]
    if any(blocked in command.lower() for blocked in blocked_keywords):
        return [TextContent(
            type="text",
            text="Error: Command contains blocked keywords for safety"
        )]
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output = f"Command: {command}\n"
        output += f"Exit Code: {result.returncode}\n\n"
        
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        
        if result.returncode != 0:
            output = f"⚠️ Command failed with exit code {result.returncode}\n\n" + output
        else:
            output = f"✓ Command succeeded\n\n" + output
        
        return [TextContent(type="text", text=output)]
        
    except subprocess.TimeoutExpired:
        return [TextContent(
            type="text",
            text=f"Error: Command timed out after {timeout} seconds"
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error executing command: {str(e)}"
        )]


def main():
    """Run the MCP server"""
    import asyncio
    
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
