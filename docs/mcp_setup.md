# MCP Setup Guide

CVA uses the Model Context Protocol (MCP) to expose security tooling to the LangGraph agent. Servers live in `src/mcp_server/` and are loaded by `src/tools/mcp_client.py`, driven by `config/mcp_servers.yaml`.

## How it works

```
main.py / auto.py
  └─ get_mcp_tools()                     # src/tools/mcp_client.py
       └─ reads config/mcp_servers.yaml  # one entry per server
            └─ for each enabled server: stdio MCP connection
                 ├─ src/mcp_server/kali.py      (cva_core)
                 └─ src/mcp_server/exploitdb.py (exploitdb)
                      └─ LangChain StructuredTools → agent
```

`get_mcp_tools()` loads **every enabled** server in `config/mcp_servers.yaml`, discovers each server's tools, converts them to LangChain `StructuredTool`s, and merges them. All MCP calls run on a dedicated background event loop (see `_get_loop()`), which keeps async MCP happy under Python 3.13.

## Design: generic tools, not one-per-binary

CVA deliberately exposes a small set of **generic** tools rather than a wrapper per binary. The agent runs `nmap`, `gobuster`, `sqlmap`, `curl`, etc. *through* `execute_shell_command`. This keeps the tool surface small and lets the agent use any installed tool without new code.

### Tools exposed today

| Tool | Server | Binary/Runtime | Description |
|---|---|---|---|
| `execute_shell_command` | `kali.py` | shell | Run any shell command (nmap, gobuster, sqlmap, …) |
| `read_local_file` | `kali.py` | — | Read a local file (scan output, wordlists) |
| `execute_sandboxed_script` | `kali.py` | Docker | Run a script inside a container |
| `search_exploits` | `exploitdb.py` | `searchsploit` | Search Exploit-DB |
| `examine_exploit` | `exploitdb.py` | `searchsploit` | Show a specific Exploit-DB entry's source |

Use `/tools` inside CVA to see exactly what loaded.

## Adding an MCP server

Add an entry under `mcp_servers:` in `config/mcp_servers.yaml` — no code changes needed:

```yaml
mcp_servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home"]
    description: "Local filesystem access"
    enabled: true
```

Each entry supports `command`, `args`, optional `env`, `description`, and `enabled`. When `command: python`, CVA runs it with the project's interpreter. Set `enabled: false` to keep a config without loading it (as the bundled `metasploit` entry does).

## Creating a custom MCP server

Any Python file using the MCP SDK works. The bundled servers use `FastMCP`:

```python
# src/mcp_server/my_tools.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-tools")

@mcp.tool()
async def my_tool(param: str) -> str:
    """Does something useful."""
    return do_something(param)

if __name__ == "__main__":
    mcp.run()
```

Then register it in `config/mcp_servers.yaml`:

```yaml
  my_tools:
    command: python
    args: ["src/mcp_server/my_tools.py"]
    enabled: true
```

## Security considerations

- `execute_shell_command` runs with the CVA process's permissions. CVA screens commands through a block/approve gate (`src/guardrails/command.py`), controllable with `/approval on|off`, but you are still responsible for scope.
- `execute_sandboxed_script` routes script execution through a Docker container; Docker must be installed and running.
- Only test systems you are authorised to test.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Failed to load MCP tools` | Run from the project root; ensure `config/mcp_servers.yaml` is valid |
| Tool returns "command not found" | Install the binary (`sudo apt install nmap`) |
| `execute_sandboxed_script` fails | Install/start Docker |
| Tool list is empty | Check that the server scripts in `src/mcp_server/` exist and import cleanly |

## Learn more

- [MCP Specification](https://modelcontextprotocol.io/)
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
