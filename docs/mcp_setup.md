# MCP (Model Context Protocol) Setup Guide

This project uses MCP (Model Context Protocol) to provide tools instead of built-in implementations. This allows you to leverage a rich ecosystem of MCP servers for various capabilities.

## What is MCP?

MCP (Model Context Protocol) is a standard protocol for connecting AI assistants to external tools and data sources. Instead of implementing tools directly, we connect to MCP servers that provide tools.

## Benefits

- **Rich Ecosystem**: Use any MCP server from the growing ecosystem
- **Separation of Concerns**: Tool implementation is separate from the CLI
- **Easy Updates**: Update tools by updating MCP servers
- **Community Tools**: Leverage community-built MCP servers
- **Security**: Tools run in separate processes with proper isolation

## Available MCP Servers

Here are some popular MCP servers you can use:

### Official MCP Servers

1. **@modelcontextprotocol/server-filesystem**
   - File operations (read, write, list, search)
   - Safe filesystem access

2. **@modelcontextprotocol/server-github**
   - GitHub API integration
   - Repository management

3. **@modelcontextprotocol/server-google-maps**
   - Google Maps integration
   - Location services

4. **@modelcontextprotocol/server-postgres**
   - PostgreSQL database access
   - SQL query execution

5. **@modelcontextprotocol/server-brave-search**
   - Web search via Brave API
   - News search

6. **@modelcontextprotocol/server-slack**
   - Slack integration
   - Channel management

### Community MCP Servers

Many more available at: https://github.com/modelcontextprotocol

## Installation

### Prerequisites

1. **Node.js** (for NPM-based MCP servers):
   ```powershell
   # Check if Node.js is installed
   node --version
   
   # If not, download from nodejs.org
   ```

2. **Python MCP package**:
   ```powershell
   # Already included in project dependencies
   uv sync
   ```

### Installing MCP Servers

Most MCP servers are distributed via NPM:

```powershell
# Install filesystem server globally
npm install -g @modelcontextprotocol/server-filesystem

# Or use npx to run without installing
npx @modelcontextprotocol/server-filesystem
```

## Configuration

### Option 1: Quick Start (No Config File)

For testing, you can run MCP servers directly and point the CLI at them using `--url`/`--tool-params`:

```powershell
# In one terminal, start an MCP server
npx -y @modelcontextprotocol/server-filesystem d:\Projects

# Note the command and use it in configuration
```

### Option 2: Configuration File (Recommended)

Create or edit `config/config.yaml` (or pass `--config PATH` to store it elsewhere):

```yaml
mcp_servers:
  # Filesystem access
  filesystem:
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-filesystem"
      - "d:\\Projects"  # Root directory to allow access
    
  # GitHub integration (requires GITHUB_TOKEN)
  github:
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-github"
    env:
      GITHUB_TOKEN: "your_github_token_here"
  
  # Web search (requires BRAVE_API_KEY)
  brave_search:
    command: npx
    args:
      - "-y"
      - "@modelcontextprotocol/server-brave-search"
    env:
      BRAVE_API_KEY: "your_brave_api_key_here"
```

> 🔌 When `type: sse`, the CLI will automatically run `command` + `args` before attempting to connect to `url`. Omit `command` if you're pointing at a hosted SSE endpoint that's already running.

### Option 3: Python MCP Servers

You can also create Python-based MCP servers:

```yaml
mcp_servers:
  custom_tools:
    command: python
    args:
      - "d:\\path\\to\\your\\mcp_server.py"
```

## Usage

Once configured, tools are automatically available:

```powershell
# List all available tools
uv run llm --list-tools

# Use a tool
uv run llm --use-tool read_file --tool-params path=README.md

# Use tools with agents
uv run llm --agent coding --chat
# Agent can now access filesystem tools
```

> ℹ️ Pass multiple parameters by repeating `--tool-params`, e.g. `--tool-params repo=owner/project --tool-params title="Bug"`.

## Example: Filesystem Server

### 1. Install
```powershell
npm install -g @modelcontextprotocol/server-filesystem
```

### 2. Configure
Add to `config/config.yaml`:
```yaml
mcp_servers:
  filesystem:
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "d:\\Projects"  # Allowed directory
```

### 3. Use
```powershell
# List tools
uv run llm --list-tools

# Read a file
uv run llm --use-tool read_file --tool-params path=src/main.py

# Search files
uv run llm --use-tool search_files --tool-params pattern="*.py" --tool-params path=src/

# Use with agent
uv run llm --agent coding "Read and analyze src/main.py"
```

## Example: GitHub Server

### 1. Get GitHub Token
1. Go to https://github.com/settings/tokens
2. Generate a new token with appropriate scopes

### 2. Configure
```yaml
mcp_servers:
  github:
    command: npx
    args:
      - "@modelcontextprotocol/server-github"
    env:
      GITHUB_TOKEN: "ghp_your_token_here"
```

### 3. Use
```powershell
# List repositories
uv run llm --use-tool list_repositories

# Create an issue
uv run llm --use-tool create_issue --tool-params repo=owner/repo title="Bug report" body="Description"

# Use with agent
uv run llm --agent coding "Create an issue in my repo about the bug I just described"
```

## Creating Custom MCP Servers

You can create your own MCP servers in Python:

```python
# my_mcp_server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server

app = Server("my-custom-server")

@app.call_tool()
async def my_tool(arguments: dict) -> list[TextContent]:
    # Your tool implementation
    result = do_something(arguments)
    return [TextContent(type="text", text=result)]

if __name__ == "__main__":
    stdio_server(app)
```

Then add to `config/config.yaml` (or your chosen config path):
```yaml
mcp_servers:
  custom:
    command: python
    args:
      - "path/to/my_mcp_server.py"
```

## Security Considerations

1. **Filesystem Access**: Only grant access to necessary directories
2. **API Keys**: Store sensitive keys in environment variables or secure config
3. **Command Execution**: Be careful with servers that execute commands
4. **Network Access**: Review what external services servers connect to

## Troubleshooting

### "No tools available"
- Check MCP servers are configured correctly
- Verify servers are installed (for NPM servers: `npm list -g`)
- Check server logs for errors

### "Failed to connect to MCP server"
- Ensure the command is correct and accessible
- Check environment variables are set
- Verify Node.js is installed (for NPM servers)

### "MCP tool execution failed"
- Check tool parameters are correct
- Review server logs
- Ensure proper permissions (for filesystem access)

## Recommended Setup

For a complete development environment:

```yaml
mcp_servers:
  # Essential: File operations
  filesystem:
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "d:\\Projects"
  
  # Development: GitHub
  github:
    command: npx
    args:
      - "@modelcontextprotocol/server-github"
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"  # From environment
  
  # Research: Web search
  brave_search:
    command: npx
    args:
      - "@modelcontextprotocol/server-brave-search"
    env:
      BRAVE_API_KEY: "${BRAVE_API_KEY}"
```

## Learn More

- MCP Documentation: https://modelcontextprotocol.io/
- MCP Servers: https://github.com/modelcontextprotocol
- Python MCP SDK: https://github.com/modelcontextprotocol/python-sdk
