# CVA — Cognitive VAPT Assistant

An AI-powered penetration-testing assistant with a Rich terminal UI. CVA guides you through the VAPT lifecycle using a LangGraph agent backed by a local LLM (Ollama) or a cloud model (OpenAI / Anthropic / Google), with security tooling exposed over the Model Context Protocol (MCP).

> **Status:** active development. CVA runs as an interactive assistant today; the autonomous (`--auto`) driver and the multi-agent supervisor are being hardened. See `docs/` for design notes.

## Features

- **LangGraph agent** — a supervisor that routes to specialist personas (recon / exploit / post-exploit / reporter), plus a single-agent and an autonomous mode.
- **Rich TUI** — colourful terminal interface with panels, markdown rendering, live `<think>` streaming, and a status line.
- **VAPT phase tracking** — automatic phase inference (Recon → Enum → Vuln → Exploit → Post-Exploit → Report) from the tools used.
- **MCP tool integration** — security tooling exposed through MCP servers (`src/mcp_server/`), driven by the agent.
- **Knowledge base (RAG)** — static pentest knowledge always on, plus optional Qdrant vector retrieval over HackTricks / PayloadsAllTheThings / GTFOBins / OWASP CheatSheets.
- **Session management** — optional MongoDB-backed sessions; always-on per-session file logs.
- **Report generation** — Markdown and HTML pentest reports from collected findings.
- **Guardrails** — prompt-injection screening on input and a block/approve gate for dangerous shell commands.
- **Multi-provider LLM** — Ollama (local) or OpenAI / Anthropic / Google (cloud) via `.env`, switchable at runtime.

## Environment

CVA is designed to run on **Kali Linux** (or another Linux pentest distro): it shells out to security tools and uses POSIX PTYs for interactive sessions. The repository can live on any filesystem, but the app and its virtualenv should be created and run from Linux.

## Quick Start

### Prerequisites

| Dependency | Required | Notes |
|---|---|---|
| Linux (Kali recommended) | ✅ | POSIX shell + PTY features are used |
| Python ≥ 3.12 | ✅ | |
| [uv](https://astral.sh/uv) | ✅ | Fast Python package manager |
| [Ollama](https://ollama.ai) | ✅ (default) | Or set a cloud provider in `.env` |
| MongoDB | Optional | Without it, sessions are not persisted (file logs still work) |
| Qdrant | Optional | Vector store for the RAG knowledge base |
| Kali security tools | For real tooling | `nmap`, `nikto`, `gobuster`, `sqlmap`, `searchsploit`, etc. |

### Installation

```bash
git clone <repo-url>
cd CVA

# Install dependencies (creates .venv)
uv sync

# Pull a local model (or configure a cloud provider in .env)
ollama pull qwen3:8b

# Copy and edit environment config
cp .env.example .env
$EDITOR .env
```

### Running CVA

```bash
# Interactive assistant
python main.py
# or via the CLI wrapper (adds flags)
python cva.py

# Autonomous run against a target
python cva.py --auto http://TARGET
```

`cva.py` flags: `--auto`, `--model <provider:model>`, `--mode supervisor|single`, `--no-guardrails`, `--no-approval`, `--debug`.

You'll be greeted by the CVA banner and the `CVA ❯` prompt. Type `/help` at any time.

## Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/target <ip/url>` | Set the pentest target |
| `/auto <target_url>` | Run an autonomous VAPT pass |
| `/run <cmd>` | Execute a raw shell command; inject output into agent context |
| `/tools` | List loaded MCP tools |
| `/progress` | Show VAPT phase progress and task tree |
| `/findings` | Findings from the current session |
| `/report [md\|html\|both]` | Generate a pentest report |
| `/sessions [list\|new\|load <id>\|save\|delete <id>]` | Manage MongoDB sessions |
| `/model <provider:model>` | Switch LLM at runtime (e.g. `/model ollama:llama3`) |
| `/mode <supervisor\|single>` | Switch agent architecture |
| `/agent` | Show the active specialist agent |
| `/kb [status\|search <q>\|update]` | Knowledge base status / search / re-ingest |
| `/log [tail N]` | View the current session log |
| `/bg [list\|status <id>]` | Background task status |
| `/think [on\|off]` | Show/hide LLM reasoning |
| `/rawtools [on\|off]` | Show/hide raw tool output |
| `/approval [on\|off]` | Toggle the command-approval gate |
| `/guardrails [on\|off]` | Toggle input guardrails |
| `/debug [on\|off]` | Toggle debug mode |
| `/settings` | Show current settings |
| `/clear` | Clear the screen |
| `/exit` | Exit CVA (auto-saves the current session) |

## Configuration

### Environment variables (`.env`)

Copy `.env.example` to `.env` and edit as needed. All settings are optional and fall back to defaults defined in `src/config.py` (Pydantic settings). Key groups: LLM provider + model, agent mode, guardrails, session/Mongo, Qdrant/KB, and UI/debug toggles. See `.env.example` for the full annotated list.

### Config files (`config/`)

| File | Purpose |
|---|---|
| `config/mcp_servers.yaml` | External MCP server definitions (loaded at startup) |

> Agent personas and app defaults are **not** YAML-driven: personas live in `src/agents/*.py` and defaults in `src/config.py`.

## Architecture

```
CVA/
├── main.py                     # Interactive entry point — terminal UI loop
├── cva.py                      # CLI wrapper (flags, --auto, --mode, --model)
├── src/
│   ├── orchestrator.py         # LangGraph supervisor + specialist graph
│   ├── auto.py                 # Autonomous ReAct driver
│   ├── config.py               # Pydantic settings (reads .env)
│   ├── agents/                 # Specialist personas: recon, exploit, post_exploit, reporter, registry
│   ├── ui/                     # cli.py (Rich TUI) + commands.py (slash commands)
│   ├── brain/                  # llm_provider.py (multi-provider) + thinking.py (<think> parsing)
│   ├── tools/                  # mcp_client.py, kb_tool.py, shell_session.py
│   ├── mcp_server/             # MCP servers: kali.py, exploitdb.py
│   ├── memory/                 # session_store.py, session_logger.py, summarizer.py
│   ├── tracker/                # task_tree.py (VAPT phase + action tracker)
│   ├── knowledge/              # rag.py, static_kb.py, vector_kb.py
│   ├── guardrails/             # command.py (dangerous-command gate), injection.py
│   └── reporting/              # generator.py (Markdown/HTML reports)
├── scripts/ingest_kb.py        # Build the Qdrant knowledge base
├── config/mcp_servers.yaml     # MCP server definitions
├── docs/                       # Extended documentation
├── tests/                      # Pytest suite
├── .env.example                # Environment template
└── pyproject.toml              # Project metadata and dependencies
```

## Available MCP tools

The MCP servers in `src/mcp_server/` currently expose a small set of **generic** tools; the agent runs specific utilities (nmap, gobuster, sqlmap, …) *through* `execute_shell_command`. Use `/tools` to see what's loaded.

| Tool | Server | Purpose |
|---|---|---|
| `execute_shell_command` | `kali.py` | Run any shell command (nmap, gobuster, sqlmap, curl, …) |
| `read_local_file` | `kali.py` | Read a local file (e.g. scan output, wordlists) |
| `execute_sandboxed_script` | `kali.py` | Run a script in a Docker sandbox |
| `search_exploits` | `exploitdb.py` | Search Exploit-DB via `searchsploit` |
| `examine_exploit` | `exploitdb.py` | Show the source of a specific Exploit-DB entry |

## VAPT workflow example

```
CVA ❯ /target 192.168.1.100
CVA ❯ Perform a basic recon scan on the target
CVA ❯ /progress
CVA ❯ Enumerate web directories
CVA ❯ /findings
CVA ❯ /report md
```

## Running tests

```bash
uv run pytest tests/ -v
```

Tests that need external services (MongoDB, Qdrant, Ollama, the MCP servers) **skip** automatically when those services aren't available. `tests/test_system.py` and `tests/test_e2e_juiceshop.py` are manual integration scripts — run them directly (`python tests/test_system.py`).

## Troubleshooting

- **"Failed to load MCP tools"** — run from the project root; ensure `src/mcp_server/kali.py` exists and the security tools are installed on the host.
- **"Failed to initialize agent"** — confirm Ollama is running (`ollama serve`), or set a cloud provider (`LLM_PROVIDER=openai`, plus the API key) in `.env`.
- **"MongoDB unavailable"** — CVA continues without session persistence; per-session file logs in `logs/` still record activity.
- **Vector KB unavailable** — run `python scripts/ingest_kb.py` with Ollama + Qdrant running to build the `cva_kb` collection; until then CVA uses the static KB only.

## License

MIT License
