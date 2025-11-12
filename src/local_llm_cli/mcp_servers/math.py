"""Built-in MCP server providing math and calculator tools"""

import asyncio
import math
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Create server instance
app = Server("builtin-math")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available math tools"""
    return [
        Tool(
            name="calculator",
            description="Evaluate mathematical expressions",
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', 'sin(pi/2)')"
                    }
                },
                "required": ["expression"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "calculator":
        return await calculator(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def calculator(arguments: dict) -> list[TextContent]:
    """Evaluate mathematical expression"""
    expression = arguments.get("expression", "")
    
    try:
        # Safe evaluation with limited namespace
        safe_dict = {
            "__builtins__": {},
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "log": math.log,
            "log10": math.log10,
            "log2": math.log2,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
            "ceil": math.ceil,
            "floor": math.floor,
            "factorial": math.factorial,
        }
        
        result = eval(expression, safe_dict)
        
        return [TextContent(
            type="text",
            text=f"Expression: {expression}\nResult: {result}\nType: {type(result).__name__}"
        )]
        
    except SyntaxError:
        return [TextContent(
            type="text",
            text=f"Error: Invalid expression syntax: {expression}"
        )]
    except NameError as e:
        return [TextContent(
            type="text",
            text=f"Error: Unknown function or variable: {str(e)}\n\nAvailable functions: abs, round, min, max, sum, pow, sqrt, sin, cos, tan, asin, acos, atan, log, log10, log2, exp, ceil, floor, factorial\nAvailable constants: pi, e"
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error: Calculation failed: {str(e)}"
        )]


def main():
    """Run the MCP server"""
    asyncio.run(stdio_server(app))


if __name__ == "__main__":
    main()
