"""Kali MCP Server — exposes core generic execution tools via FastMCP."""

import subprocess
import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cva-core-tools")


@mcp.tool()
async def execute_shell_command(command: str) -> str:
    """Execute a shell command on the local system.
    
    Use this to run any Kali command (e.g., nmap, gobuster, nikto, crackmapexec).
    You have full bash access. If output is likely to be very long, consider redirecting 
    it to a file (e.g., '> output.txt') and reading it later.
    
    Args:
        command: The shell command to execute
    """
    try:
        # 5 minute timeout since pentest tools can be slow
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=300
        )
        
        output = ""
        if result.stdout:
            output += f"[stdout]\n{result.stdout}\n"
        if result.stderr:
            output += f"[stderr]\n{result.stderr}\n"
            
        if not output:
            output = f"(Command exited with code {result.returncode} but produced no output)"
            
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 300 seconds."
    except Exception as e:
        return f"Error executing command: {e}"


@mcp.tool()
async def read_local_file(filepath: str, lines: int = 500) -> str:
    """Read the contents of a local file. Useful for reviewing tool outputs saved to disk.
    
    Args:
        filepath: Absolute or relative path to the file
        lines: Maximum number of lines to read (default 500) to avoid context bloat
    """
    if not os.path.exists(filepath):
        return f"Error: File not found: {filepath}"
    
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = []
            for i, line in enumerate(f):
                if i >= lines:
                    content.append(f"\n... (file truncated after {lines} lines)")
                    break
                content.append(line)
            return "".join(content)
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
async def execute_sandboxed_script(script: str, language: str = "python", network: str = "bridge") -> str:
    """Execute a script inside a Docker sandbox.
    
    Args:
        script: The script content to execute
        language: Programming language (python or bash)
        network: Network mode ('bridge' by default to reach targets, use 'none' for severe isolation)
    """
    try:
        import docker
        client = docker.from_env()
        
        image = "python:3.12-slim" if language == "python" else "bash:latest"
        cmd = ["python", "-c", script] if language == "python" else ["bash", "-c", script]
        
        container = client.containers.run(
            image=image,
            command=cmd,
            detach=False,
            remove=True,
            network_mode=network,  # bridge allows outbound traffic to target, none isolates
            mem_limit="256m",
            cpu_period=100000,
            cpu_quota=50000,
            stdout=True,
            stderr=True,
        )
        return container.decode("utf-8") if isinstance(container, bytes) else str(container)
    except Exception as e:
        # If docker isn't running or installed, gracefully inform
        if "Connection refused" in str(e) or "No such file or directory" in str(e):
            return "Sandbox error: Docker is not running or not installed."
        return f"Sandbox error: {e}"


if __name__ == "__main__":
    mcp.run()
