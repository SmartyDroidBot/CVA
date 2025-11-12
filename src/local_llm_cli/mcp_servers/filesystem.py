"""Built-in MCP server providing file system tools"""

import asyncio
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Create server instance
app = Server("builtin-filesystem")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available file system tools"""
    return [
        Tool(
            name="read_file",
            description="Read the contents of a text file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="write_file",
            description="Write content to a text file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8"
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Append to file instead of overwriting",
                        "default": False
                    }
                },
                "required": ["path", "content"]
            }
        ),
        Tool(
            name="list_directory",
            description="List files and directories in a path",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list",
                        "default": "."
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g., '*.py')",
                        "default": "*"
                    }
                },
                "required": []
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "read_file":
        return await read_file(arguments)
    elif name == "write_file":
        return await write_file(arguments)
    elif name == "list_directory":
        return await list_directory(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def read_file(arguments: dict) -> list[TextContent]:
    """Read file contents"""
    path = arguments.get("path")
    encoding = arguments.get("encoding", "utf-8")
    
    try:
        file_path = Path(path)
        
        if not file_path.exists():
            return [TextContent(
                type="text",
                text=f"Error: File not found: {path}"
            )]
        
        if not file_path.is_file():
            return [TextContent(
                type="text",
                text=f"Error: Path is not a file: {path}"
            )]
        
        content = file_path.read_text(encoding=encoding)
        
        return [TextContent(
            type="text",
            text=f"File: {file_path.absolute()}\nSize: {len(content)} bytes\nLines: {len(content.splitlines())}\n\n{content}"
        )]
        
    except UnicodeDecodeError:
        return [TextContent(
            type="text",
            text=f"Error: Failed to decode file with encoding: {encoding}"
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error reading file: {str(e)}"
        )]


async def write_file(arguments: dict) -> list[TextContent]:
    """Write to file"""
    path = arguments.get("path")
    content = arguments.get("content")
    encoding = arguments.get("encoding", "utf-8")
    append = arguments.get("append", False)
    
    try:
        file_path = Path(path)
        
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if append:
            file_path.write_text(file_path.read_text(encoding=encoding) + content, encoding=encoding)
            mode = "appended to"
        else:
            file_path.write_text(content, encoding=encoding)
            mode = "written to"
        
        return [TextContent(
            type="text",
            text=f"Successfully {mode} {file_path.absolute()}\nSize: {len(content)} bytes"
        )]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error writing file: {str(e)}"
        )]


async def list_directory(arguments: dict) -> list[TextContent]:
    """List directory contents"""
    path = arguments.get("path", ".")
    pattern = arguments.get("pattern", "*")
    
    try:
        dir_path = Path(path)
        
        if not dir_path.exists():
            return [TextContent(
                type="text",
                text=f"Error: Directory not found: {path}"
            )]
        
        if not dir_path.is_dir():
            return [TextContent(
                type="text",
                text=f"Error: Path is not a directory: {path}"
            )]
        
        # List files matching pattern
        files = []
        for item in dir_path.glob(pattern):
            item_type = "file" if item.is_file() else "directory"
            size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
            files.append(f"  {item.name} ({item_type}){size}")
        
        result = f"Directory: {dir_path.absolute()}\nPattern: {pattern}\nItems: {len(files)}\n\n"
        result += "\n".join(files) if files else "  (empty)"
        
        return [TextContent(type="text", text=result)]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error listing directory: {str(e)}"
        )]


def main():
    """Run the MCP server"""
    asyncio.run(stdio_server(app))


if __name__ == "__main__":
    main()
