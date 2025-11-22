# Local LLM CLI

A modular, extensible command-line interface for local Large Language Models with MCP (Model Context Protocol) tool integration.

## Features

- **Multiple Backends**: Support for Ollama and llama.cpp
- **Agent System**: Different AI personas with customizable prompts and behaviors
- **MCP Tool Integration**: Dynamic tool loading and automatic tool calls from MCP servers
- **Built-in Tools**: File operations, math calculator, system commands
- **Typer + Rich CLI**: Modern UX with colorized output, streaming, and contextual help
- **Configuration System**: Pydantic-backed YAML/JSON config with validation and defaults
- **Plugin Architecture**: Extensible through custom plugins
- **Interactive Chat**: Multi-turn conversations with context
- **Flexible I/O**: Single prompts, file input, or interactive chat mode

## Quick Start

### Installation

```powershell
# Clone the repository
git clone <repo-url>
cd CVA

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Prerequisites

1. **Ollama** (recommended): Install from [ollama.ai](https://ollama.ai)
   ```powershell
   ollama pull llama2
   ```

2. **Python 3.10+**: The project requires Python 3.10 or higher

### Basic Usage

```powershell
# Initialize configuration (creates config/config.yaml plus companion files)
uv run llm --init-config

# List available tools
uv run llm --list-tools

# List available agents
uv run llm --list-agents

# Single prompt (positional argument)
uv run llm "What is 2+2?"

# Interactive chat
uv run llm --chat

# Use specific agent
uv run llm --chat --agent coding

# Use specific model
uv run llm --chat --model qwen3:8b

# Inspect available models from the active backend
uv run llm --list-models

# Execute an MCP tool
uv run llm --use-tool read_file --tool-params path=README.md

# Ask the assistant to call MCP tools automatically
uv run llm "Summarize README.md"  # LLM will emit a <<CALL_TOOL ...>> directive when needed
```

## Configuration

By default, configuration lives in the `config/` directory within this repository. Pass `--config PATH` to store the base config elsewhere (e.g., `%APPDATA%\llm\config.yaml`). The manager now keeps related data in three files so MCP settings and system prompts can evolve independently:

| File | Purpose |
| --- | --- |
| `config/config.yaml` | Backend, defaults, and global flags |
| `config/agents.yaml` | Agent definitions (temperatures, system prompts, preferred models) |
| `config/mcp_servers.yaml` | MCP server definitions |

Example `config/config.yaml`:

```yaml
backend:
  type: ollama
  url: http://localhost:11434
  default_model: qwen3:8b
  timeout: 120
default_agent: general
verbose: false
color_output: true
```

Example `config/agents.yaml`:

```yaml
general:
  temperature: 0.7
  system_prompt: "You are a helpful AI assistant."

coding:
  temperature: 0.2
  preferred_model: codellama
  system_prompt: "You are an expert programmer."

conversational:
  temperature: 0.8
  system_prompt: "You are a friendly conversational AI."
```

Example `config/mcp_servers.yaml`:

```yaml
filesystem:
  type: stdio
  command: python
  args: ["-m", "cva_cli.mcp_servers.filesystem"]
  enabled: false

math:
  type: stdio
  command: python
  args: ["-m", "cva_cli.mcp_servers.math"]
  enabled: false

system:
  type: stdio
  command: python
  args: ["-m", "cva_cli.mcp_servers.system"]
  enabled: false
```

> 💡 **Tip:** Set `enabled: true` for any MCP server you want auto-started. You can also provide `url` and `headers` to connect to SSE-capable remote servers instead of spawning a local process.


## Built-in MCP Servers

These Python reference servers ship with the project but remain disabled until you opt-in via the config file:

### Filesystem
- `read_file`: Read text files
- `write_file`: Write/append to files
- `list_directory`: List directory contents with glob patterns

### Math
- `calculator`: Evaluate mathematical expressions safely

### System
- `system_info`: Get platform/Python information
- `shell_command`: Execute shell commands (with safety checks)

## Agents

### General
- **Temperature**: 0.7
- **Use Case**: General-purpose assistance
- **System Prompt**: Balanced, helpful AI assistant

### Coding
- **Temperature**: 0.2 (precise)
- **Preferred Model**: codellama
- **Use Case**: Programming, code review, debugging
- **System Prompt**: Expert programmer providing clear, efficient code

### Conversational
- **Temperature**: 0.8 (creative)
- **Use Case**: Casual conversation, brainstorming
- **System Prompt**: Friendly, engaging conversational AI

## Advanced Usage

### Automatic MCP Tool Calls

During normal prompts or chat sessions the assistant can now invoke MCP tools on its own. To trigger a tool call, the model must emit a directive that looks like this:

```
<<CALL_TOOL tool_name {"argument": "value"}>>
```

When the CLI detects this pattern it will execute the requested MCP tool (up to three calls per response), stream the results back into the conversation, and then re-query the LLM so it can finish the answer with the new information. The tool catalog is still available via `--list-tools`, and you can execute a tool manually at any time with `--use-tool`.

### Custom MCP Servers

Add external MCP servers to your config:

```yaml
mcp_servers:
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: "your-token"
    enabled: true
```

### Creating Custom Agents

See `docs/creating_agents.md` for detailed instructions on creating custom agent personas.

### Plugin Development

See `src/cva_cli/plugins/_template.py` for a plugin template.

## Command-Line Options

| Option | Description |
| --- | --- |
| `prompt` *(positional)* | Words following the command form the prompt (e.g., `llm "Hello"`). |
| `--config PATH` | Override the config file path (defaults to `config/config.yaml`). |
| `--init-config` | Write a fresh config and exit. |
| `--backend`, `--url`, `--model` | Override backend type, API URL, or model name for this run. |
| `--agent` | Choose the registered agent persona. |
| `--temperature`, `--max-tokens` | Override sampling parameters per run. |
| `--no-stream` | Disable streaming token output. |
| `--system TEXT` | Provide a one-off system prompt override. |
| `--chat` | Start interactive chat mode (defaults on if no prompt is provided). |
| `--file PATH` | Read prompt text from a file. |
| `--list-models` / `--list-backends` / `--list-agents` | Inspect available models/backends/agents and exit. |
| `--list-tools` | Discover the aggregated MCP tool catalog. |
| `--tool-info NAME` | Show metadata for a specific tool. |
| `--use-tool NAME` | Execute a tool directly; combine with `--tool-params key=value` pairs. |
| `--verbose` | Emit extra debug information (also influences MCP warnings). |

## Architecture

```
local-llm-cli/
├── backends/          # LLM backend implementations (Ollama, llama.cpp)
├── agents/            # Agent system with personas
├── mcp/               # MCP client and server management
├── mcp_servers/       # Built-in MCP tool servers
├── config/            # Configuration management
├── plugins/           # Plugin system
└── core/              # CLI core and main logic
```

## Troubleshooting

### "No module named 'ollama'"
This is expected - the CLI uses HTTP requests to Ollama, not the Python client.

### "Model not found"
Pull the model with Ollama:
```powershell
ollama pull llama2
```

### "No tools available"
Run `--init-config` to create default configuration with built-in MCP servers.

### MCP server connection errors
- Ensure Python is in your PATH
- Check that the MCP servers are enabled in config
- Try with `--verbose` for detailed error messages

## Development

### Project Structure
- **Modular**: Separation of concerns (backends, agents, tools, config)
- **Extensible**: Plugin system and custom agents
- **Type-safe**: Full type hints for better IDE support
- **Async-ready**: MCP integration uses async/await

### Running Tests & Checks
```powershell
# Unit tests (currently minimal; add your own!)
uv run pytest

# Linting / type checks (optional but recommended)
uv run ruff check
uv run mypy

# Quick CLI smoke tests
uv run llm --list-tools
uv run llm "Calculate sqrt(144)"
uv run llm --chat --agent coding
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Links

- **Ollama**: https://ollama.ai
- **llama.cpp**: https://github.com/ggerganov/llama.cpp
- **MCP Specification**: https://modelcontextprotocol.io
- **Documentation**: See `docs/` directory

## Acknowledgments

- Built with the Model Context Protocol (MCP)
- Inspired by Google's Gemini CLI
- Powered by Ollama and llama.cpp
