# MCP Setup Guide

CVA uses the Model Context Protocol (MCP) to expose Kali Linux security tools to the LangGraph agent. Tools are implemented in `src/mcp_server/kali.py` and loaded into the agent by `src/tools/mcp_client.py`.

## How It Works

```
main.py
  └─ get_mcp_tools()                   # src/tools/mcp_client.py
       └─ stdio MCP connection
            └─ src/mcp_server/kali.py  # Kali tools server
                 └─ LangChain StructuredTools → LangGraph agent
```

`McpClient` connects to `kali.py` over stdio, discovers available tools, converts them to LangChain `StructuredTool` objects, and passes them to the `Orchestrator`. The agent then calls them through the standard ReAct tool-use loop.

## Built-in Kali Tools

These tools are available immediately after `uv sync` as long as the underlying binaries are installed on the host:

| Tool | Binary Required | Description |
|---|---|---|
| `nmap_scan` | `nmap` | TCP/UDP port scanning |
| `nikto_scan` | `nikto` | Web server vulnerability scan |
| `gobuster_dir` | `gobuster` | Directory/file brute-forcing |
| `ffuf_fuzz` | `ffuf` | Web fuzzing |
| `sqlmap_scan` | `sqlmap` | SQL injection detection |
| `hydra_bruteforce` | `hydra` | Login brute-forcing |
| `whatweb_scan` | `whatweb` | Web technology fingerprinting |
| `curl_request` | `curl` | HTTP request runner |
| `search_exploitdb` | `searchsploit` | Exploit-DB search |
| `search_web` | — | Web search via API |
| `execute_shell_command` | — | Raw shell command execution |
| `execute_sandboxed_script` | Docker | Script execution in a container |
| `hash_identify` | — | Hash type identification |

Use `/tools` inside CVA to see exactly which tools loaded and their descriptions.

## Adding External MCP Servers

Edit `config/mcp_servers.yaml` to add extra MCP servers. CVA's MCP client currently connects to `src/mcp_server/kali.py` by default. To route traffic to a different server, update `McpClient.__init__` in `src/tools/mcp_client.py`:

```python
class McpClient:
    def __init__(self, server_script: str = "src/mcp_server/kali.py"):
```

### Example — add a filesystem MCP server

1. Install the server:
   ```bash
   npm install -g @modelcontextprotocol/server-filesystem
   ```

2. Add its YAML entry to `config/mcp_servers.yaml`:
   ```yaml
   filesystem:
     command: npx
     args: ["-y", "@modelcontextprotocol/server-filesystem", "/home"]
     enabled: true
   ```

3. To load it alongside `kali.py`, instantiate multiple `McpClient` objects in `src/tools/mcp_client.py` and merge the returned tool lists.

## Creating a Custom MCP Server

Any Python file that implements the MCP stdio protocol can serve as a tool source:

```python
# src/mcp_server/my_tools.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("my-tools")

@app.list_tools()
async def list_tools():
    return [Tool(name="my_tool", description="Does something", inputSchema={
        "type": "object",
        "properties": {"param": {"type": "string"}},
        "required": ["param"],
    })]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "my_tool":
        result = do_something(arguments["param"])
        return [TextContent(type="text", text=result)]

if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(app))
```

Then point `McpClient` at it:

```python
client = McpClient(server_script="src/mcp_server/my_tools.py")
```

## Security Considerations

- `execute_shell_command` runs commands with the permissions of the CVA process — use with care and only against authorised targets
- Set `SANDBOX_ENABLED=true` in `.env` to route script execution through a Docker container
- Only test systems you are authorised to test

## Troubleshooting

| Problem | Fix |
|---|---|
| `Failed to load MCP tools` | Run `python main.py` from the project root |
| Tool returns "command not found" | Install the binary (`sudo apt install nmap`) |
| `execute_sandboxed_script` fails | Install Docker and set `SANDBOX_ENABLED=true` |
| Tool list is empty | Check that `src/mcp_server/kali.py` exists and is valid Python |

## Learn More

- [MCP Specification](https://modelcontextprotocol.io/)
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Tool Servers](https://github.com/modelcontextprotocol)
