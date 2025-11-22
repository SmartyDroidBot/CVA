import sys
import subprocess
import platform
from typing import Any, List
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("cva-shell")

@mcp.tool()
def execute_windows_command(command: str) -> str:
    """
    Execute a PowerShell command on Windows.
    
    Args:
        command: The PowerShell command to execute.
        
    Returns:
        The stdout and stderr of the command.
    """
    if platform.system() != "Windows":
        return "Error: This tool is only available on Windows."
    
    try:
        # Use powershell to execute the command
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            check=False
        )
        output = result.stdout
        if result.stderr:
            output += f"\nStderr: {result.stderr}"
        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"

@mcp.tool()
def execute_linux_command(command: str) -> str:
    """
    Execute a Bash command on Linux/Unix.
    
    Args:
        command: The Bash command to execute.
        
    Returns:
        The stdout and stderr of the command.
    """
    if platform.system() == "Windows":
        return "Error: This tool is only available on Linux/Unix."
    
    try:
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True,
            text=True,
            check=False
        )
        output = result.stdout
        if result.stderr:
            output += f"\nStderr: {result.stderr}"
        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"

def main():
    mcp.run()

if __name__ == "__main__":
    main()
