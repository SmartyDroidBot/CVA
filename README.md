# CVA — Cognitive VAPT Assistant

An AI-powered penetration testing assistant with a Rich terminal UI. CVA guides you through the full VAPT lifecycle using a ReAct agent backed by Ollama (or cloud LLMs) and a suite of Kali Linux security tools exposed via the Model Context Protocol (MCP).

## Features

- **ReAct Agent** — LangGraph-based reasoning loop that selects tools, explains its thinking, and summarizes findings
- **Rich TUI** — Gemini CLI-style terminal interface with colour, panels, markdown rendering, and a status line
- **VAPT Lifecycle Tracking** — Automatic phase tracking (Recon → Enum → Vuln → Exploit → Post-Exploit → Report)
- **MCP Tool Integration** — Security tools exposed through `src/mcp_server/kali.py` (nmap, nikto, gobuster, sqlmap, hydra, ffuf, searchsploit, and more)
- **Session Management** — MongoDB-backed sessions to save/resume pentest conversations
- **Report Generation** — Markdown and HTML pentest reports from collected findings
- **Multi-Provider LLM** — Ollama (local) or OpenAI / Anthropic / Google (cloud) via `.env`
- **Context Summarisation** — Auto-compresses long conversations to preserve context window

## Quick Start

### Prerequisites

| Dependency | Required | Notes |
|---|---|---|
| Python ≥ 3.12 | ✅ | |
| [uv](https://astral.sh/uv) | ✅ | Fast Python package manager |
| [Ollama](https://ollama.ai) | ✅ (default) | Or set a cloud provider in `.env` |
| MongoDB | Optional | Sessions stored in-memory without it |
| Qdrant | Optional | Vector store for RAG knowledge base |
| Kali Linux tools | Required for tools | `nmap`, `nikto`, `gobuster`, etc. |

### Installation

```bash
# Clone the repo
git clone <repo-url>
cd CVA

# Install dependencies
uv sync

# Pull a model
ollama pull qwen3:8b

# Copy and edit environment config
cp .env.example .env
$EDITOR .env
```

### Running CVA

```bash
python main.py
```

You will be greeted by the CVA banner and the `CVA ❯` prompt. Type `/help` at any time to see available commands.

## Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/target <ip/url>` | Set the pentest target |
| `/run <cmd>` | Execute a raw shell command and auto-parse output |
| `/tools` | List all loaded MCP tools by category |
| `/progress` | Show VAPT phase progress and recent actions |
| `/findings` | Summary of findings from the current session |
| `/sessions [list\|new\|load\|save\|delete]` | Manage MongoDB sessions |
| `/report [md\|html\|both]` | Generate a pentest report |
| `/model <provider:model>` | Switch LLM at runtime (e.g. `/model ollama:llama3`) |
| `/debug [on\|off]` | Toggle raw tool-output display |
| `/settings` | Show current settings |
| `/clear` | Clear the screen |
| `/exit` | Exit CVA (auto-saves current session) |

## Configuration

### Environment Variables (`.env`)

Copy `.env.example` to `.env` and edit as needed:

```dotenv
# LLM Provider: ollama | openai | anthropic | google
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434

# Cloud LLM keys (uncomment as needed)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=...

# Optional services
MONGO_URI=mongodb://localhost:27017
QDRANT_HOST=localhost
QDRANT_PORT=6333

# App settings
DEBUG_MODE=false
SANDBOX_ENABLED=false
```

### Config Files (`config/`)

| File | Purpose |
|---|---|
| `config/config.yaml` | App defaults (timeout, etc.) |
| `config/agents.yaml` | Agent personas (name, system prompt, temperature) |
| `config/mcp_servers.yaml` | External MCP server definitions |

## Architecture

```
CVA/
├── main.py                   # Entry point — terminal UI loop
├── src/
│   ├── orchestrator.py       # LangGraph ReAct agent
│   ├── config.py             # Pydantic settings (reads .env)
│   ├── state.py              # Shared state types
│   ├── ui/
│   │   ├── cli.py            # Rich TUI: banner, panels, input
│   │   └── commands.py       # Slash command handler
│   ├── brain/
│   │   ├── llm_provider.py   # Multi-provider LLM factory
│   │   └── thinking.py       # Parse <think> blocks from LLM output
│   ├── tools/
│   │   └── mcp_client.py     # Bridges MCP server tools to LangChain
│   ├── mcp_server/
│   │   └── kali.py           # MCP server: Kali Linux security tools
│   ├── memory/
│   │   ├── session_store.py  # MongoDB session persistence
│   │   └── summarizer.py     # LLM-based context compressor
│   ├── tracker/
│   │   └── task_tree.py      # VAPT phase + action tracker
│   ├── knowledge/
│   │   ├── rag.py            # Qdrant RAG retrieval
│   │   └── static_kb.py      # Static pentest knowledge base
│   ├── parser/
│   │   └── intelligent_parser.py  # Parses raw tool output into findings
│   └── reporting/
│       └── generator.py      # Markdown/HTML report generator
├── config/                   # YAML configs
├── docs/                     # Extended documentation
├── tests/                    # Pytest test suite
├── .env.example              # Environment variable template
└── pyproject.toml            # Project metadata and dependencies
```

## Available MCP Tools

Tools are provided by `src/mcp_server/kali.py` and loaded automatically on startup. Use `/tools` inside CVA to see what's loaded.

| Category | Tools |
|---|---|
| **Recon** | `nmap_scan`, `whatweb_scan`, `curl_request` |
| **Enumeration** | `gobuster_dir`, `ffuf_fuzz` |
| **Vulnerability** | `nikto_scan`, `search_exploitdb` |
| **Exploitation** | `sqlmap_scan`, `hydra_bruteforce`, `execute_sandboxed_script` |
| **Research** | `search_web` |
| **Utility** | `execute_shell_command`, `hash_identify` |

## VAPT Workflow Example

```
CVA ❯ /target 192.168.1.100
CVA ❯ Perform a basic recon scan on the target
CVA ❯ /progress
CVA ❯ Enumerate web directories
CVA ❯ /findings
CVA ❯ /report md
```

## Running Tests

```bash
uv run pytest tests/ -v
```

## Troubleshooting

### "Failed to load MCP tools"
- Ensure `python main.py` is run from the project root
- Check that `src/mcp_server/kali.py` is present
- Security tools (nmap, nikto, etc.) must be installed on the host

### "Failed to initialize agent"
- Confirm Ollama is running: `ollama serve`
- Or set a cloud provider via `LLM_PROVIDER=openai` in `.env`

### "MongoDB not available"
- CVA falls back to in-memory sessions — you can still use `/sessions new` but data is lost on exit

## License

MIT License
