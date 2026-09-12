# CVA — Cognitive VAPT Assistant

An AI-powered penetration-testing assistant with a Rich terminal UI. CVA plans and executes the VAPT lifecycle with a single planner/executor engine, backed by whichever LLM you configure — a local model (Ollama) or a cloud model (OpenAI / Anthropic / Google) — with security tooling exposed over the Model Context Protocol (MCP).

## Features

- **Planner/executor engine** — one engine (`src/engine.py`) plans an engagement into a task graph and executes each task with a bounded ReAct loop. Both modes run on it: **copilot** (interactive, turn-by-turn) and **autonomous** (`--auto`).
- **Model-agnostic** — Ollama (local) or OpenAI / Anthropic / Google (cloud), chosen in `.env` and switchable at runtime with `/model`. CVA never hard-codes a provider.
- **Rich TUI** — colourful terminal interface with panels, markdown rendering, live `<think>` streaming, and a status line.
- **VAPT task graph & phase tracking** — engagements are a dependency graph of tasks; phase (Recon → Enum → Vuln → Exploit → Post-Exploit → Report) is inferred from the commands run.
- **MCP tool integration** — generic tooling exposed through MCP servers (`src/mcp_server/`); the agent runs nmap/gobuster/sqlmap/etc. through `execute_shell_command`.
- **Knowledge base (RAG)** — a local **SQLite FTS5** full-text index over HackTricks / PayloadsAllTheThings / GTFOBins / OWASP CheatSheets, behind a pluggable `KnowledgeSource` interface (no external services required).
- **Structured findings** — the agent records confirmed findings via a `record_finding` tool; reports are generated from that evidence, not keyword guesses.
- **Session management** — optional MongoDB-backed sessions; always-on per-session file logs.
- **Report generation** — Markdown and HTML pentest reports.
- **Guardrails** — prompt-injection screening on input, untrusted-data fencing of tool output, and a block/approve gate for dangerous shell commands.

## Environment

CVA is designed to run on **Kali Linux** (or another Linux pentest distro): it shells out to security tools and uses POSIX PTYs for interactive sessions. The repository can live on any filesystem, but the app and its virtualenv should be created and run from Linux.

## Quick Start

### Prerequisites

| Dependency | Required | Notes |
|---|---|---|
| Linux (Kali recommended) | ✅ | POSIX shell + PTY features are used |
| Python ≥ 3.12 | ✅ | |
| [uv](https://astral.sh/uv) | ✅ | Fast Python package manager |
| An LLM | ✅ | Ollama locally, **or** a cloud key (OpenAI / Anthropic / Google) — your choice in `.env` |
| MongoDB | Optional | Without it, sessions are not persisted (file logs still work) |
| Docker | Optional | Runs MongoDB; `demo.sh` uses it if present |
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

# Autonomous run against an authorized target you provide
python cva.py --auto <target-url>
```

`cva.py` flags: `--auto <target>`, `--model <provider:model>`, `--type {auto,web,network,api,host}`, `--scope <extra,targets>`, `--no-guardrails`, `--no-approval`, `--debug`.

You'll be greeted by the CVA banner and the `CVA ❯` prompt. Type `/help` at any time.

> **Targets are yours to provide.** CVA ships no target and assumes none — stand up your own authorized lab/target separately and pass its URL. Only test systems you are authorized to test.

## Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/target <ip/url>` | Set the pentest target (auto-detects the engagement type) |
| `/scope [type\|add\|out]` | Show/set engagement scope (`/scope web\|network\|api\|host`, `/scope add <host>`, `/scope out <host>`) |
| `/auto <target_url>` | Run an autonomous VAPT pass |
| `/run <cmd>` | Execute a raw shell command; inject output into agent context |
| `/tools` | List loaded MCP tools |
| `/progress` | Show VAPT phase progress and task tree |
| `/findings` | Findings from the current session |
| `/report [md\|html\|both]` | Generate a pentest report |
| `/sessions [list\|new\|load <id>\|save\|delete <id>]` | Manage MongoDB sessions |
| `/model <provider:model>` | Switch LLM at runtime (e.g. `/model ollama:llama3`) |
| `/agent` | Show the current VAPT phase |
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

## Choosing your LLM (model-agnostic)

CVA never hard-codes a provider. You choose one in your config file `.env` (copied from `.env.example`), and everything else respects it:

```dotenv
# .env — pick ONE provider and its default model.
LLM_PROVIDER=ollama            # ollama | openai | anthropic | google

# Local (default): needs Ollama running and the model pulled.
OLLAMA_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434

# Cloud: set LLM_PROVIDER above and the matching key + model.
# OPENAI_API_KEY=sk-...        # OPENAI_MODEL=gpt-4o
# ANTHROPIC_API_KEY=sk-ant-... # ANTHROPIC_MODEL=claude-sonnet-4-20250514
# GOOGLE_API_KEY=...           # GOOGLE_MODEL=gemini-2.5-flash
```

Override for a single run with `python cva.py --model <provider:model>`, or switch live with `/model <provider:model>`. A capable model is recommended for reliable multi-step tool use; small local models can loop or emit malformed tool calls.

CVA runs a **reachability preflight** at startup: `--auto` aborts with a clear message if the LLM is unreachable (so it never produces an empty report), and interactive mode warns but lets you fix it with `/model`.

### Running the LLM from WSL

If CVA runs inside **WSL** (e.g. Kali) but Ollama runs on the **Windows host**, `localhost:11434` inside WSL is *not* the host — connections are refused (`Errno 111`) and the LLM appears down. Fix it one of two ways:

- **WSL mirrored networking (preferred, Win 11 22H2+):** add to `%UserProfile%\.wslconfig`:
  ```ini
  [wsl2]
  networkingMode=mirrored
  ```
  then `wsl --shutdown` and reopen. `localhost:11434` now reaches the host; no `.env` change.
- **Point at the host IP:** on Windows set `OLLAMA_HOST=0.0.0.0` (so Ollama listens on all interfaces) and allow it through the firewall, then in `.env` set `OLLAMA_BASE_URL=http://<windows-host-ip>:11434` (the WSL→host gateway from `ip route show default`; it can change on restart unless mirrored networking is on).

Simplest of all: run Ollama **inside** the WSL distro so `localhost` just works.

## Configuration

All settings are optional and fall back to defaults in `src/config.py` (Pydantic settings, read from `.env`): LLM provider + models, guardrails, session/Mongo, knowledge base (`KB_BACKEND`/`KB_DB_PATH`), and UI/debug toggles. See `.env.example` for the full annotated list. The only YAML config is `config/mcp_servers.yaml` (MCP server definitions); agent personas live in `src/agents/*.py`.

## Architecture

Both modes run on one engine — a planner decomposes the goal into a task graph; a per-task ReAct executor runs each task, records findings, and the reporter renders them. Knowledge is pluggable behind an interface; tool output is fenced as untrusted data before it re-enters the model.

```
goal / target
      │
      ▼
┌──────────────┐   read / write   ┌──────────────────────┐
│  PLANNER     │◄────────────────►│  TASK GRAPH (DAG)     │  src/tracker/task_tree.py
└──────┬───────┘                   └──────────┬───────────┘
       │ next ready task                       │ log actions
       ▼                                        ▼
┌──────────────┐   tool calls     ┌──────────────────────┐
│  EXECUTOR    │─────────────────►│  MCP TOOLS + KB       │  execute_shell_command, search_*,
│ (ReAct loop) │◄─────────────────│  (fenced as data)     │  search_knowledge_base (FTS5)
└──────┬───────┘   observations    └──────────────────────┘
       │ record_finding
       ▼
┌──────────────┐                   ┌──────────────────────┐
│  REPORTER    │◄──────────────────│  EVIDENCE STORE       │  src/memory/evidence.py
└──────────────┘                   └──────────────────────┘
```

```
CVA/
├── main.py                     # Interactive (copilot) entry point — terminal UI loop
├── cva.py                      # CLI wrapper (--auto, --model, --no-guardrails, --no-approval)
├── src/
│   ├── engine.py               # PentestEngine — planner + per-task ReAct executor (both modes)
│   ├── auto.py                 # Autonomous runner (drives the engine, Rich UI)
│   ├── config.py               # Pydantic settings (reads .env)
│   ├── agents/                 # Specialist personas: recon, exploit, post_exploit, reporter, registry
│   ├── ui/                     # cli.py (Rich TUI) + commands.py (slash commands)
│   ├── brain/                  # llm_provider.py (multi-provider) + thinking.py (<think> parsing)
│   ├── tools/                  # mcp_client.py, kb_tool.py, finding_tool.py, shell_session.py
│   ├── mcp_server/             # MCP servers: kali.py, exploitdb.py
│   ├── memory/                 # session_store.py, session_logger.py, summarizer.py, evidence.py
│   ├── tracker/                # task_tree.py (task graph + phase tracking)
│   ├── knowledge/              # base.py (KnowledgeSource), fts_kb.py (FTS5), rag.py (merger)
│   ├── guardrails/             # command.py (dangerous-command gate), injection.py (+ output screening)
│   └── reporting/              # generator.py (Markdown/HTML reports)
├── scripts/ingest_kb.py        # Build the FTS5 knowledge-base index
├── config/mcp_servers.yaml     # MCP server definitions
├── demo.sh · Makefile          # One-command demo + convenience targets
├── docs/ · tests/ · .env.example · pyproject.toml
```

### How it compares

CVA's shape follows the current field — a deterministic harness around the model rather than one big prompt:

| System | Shared idea |
|---|---|
| **VulnBot** | planner + executor over a penetration task graph, runs on open models |
| **PentestGPT / V2** | explicit task tree to prevent "context collapse" |
| **HackingBuddyGPT** | persistent planner + focused per-task executor |
| **CAI / PentAGI** | model-agnostic (local or cloud), tools behind a clean layer |

## Scoped engagements

CVA runs the methodology that fits the target instead of a generic one. It infers an
**engagement type** from the target and plans from a curated, per-type template (so a web app
gets HTTP tooling, not nmap sweeps, and a network range starts with host/service discovery):

| Type | Detected from | Methodology |
|---|---|---|
| `web` | `http(s)://…` | fingerprint → content discovery → web vulns (SQLi/XSS/auth/IDOR/SSRF) |
| `api` | URL with `/api`, `/graphql`, `/openapi`… | schema discovery → authz/BOLA → injection → rate-limit |
| `network` | IP / CIDR / bare host | host discovery → service scan → enumeration → version CVEs |
| `host` | explicit `--type host` | local enum → privilege escalation → credential harvest |

Set it explicitly with `--type` / the `/scope` command, or let it auto-detect from `/target`.
The scope is injected into every agent turn, and **commands aimed at out-of-scope hosts are
hard-blocked** before they run (shown on screen). This design follows the Structured Attack
Tree result ([arXiv 2509.07939](https://arxiv.org/abs/2509.07939)): a code-owned methodology
substantially raises task completion and cuts wasted queries versus free-form planning. Add or
edit profiles in `src/scope.py` (`PROFILES`).

## Demo

CVA ships no target — stand up your own authorized target first, then:

```bash
# 1. choose your model in .env (see "Choosing your LLM")
cp .env.example .env && $EDITOR .env
# 2. run an autonomous engagement against your target and get a report
./demo.sh <target-url>          # or:  make demo TARGET=<target-url>
```

`demo.sh` verifies your configured provider is ready, starts optional MongoDB (if Docker is present), builds the FTS5 knowledge base on first run, runs the engagement, and prints the report path in `reports/`.

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
CVA ❯ /target <ip-or-url>
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

Tests that need external services (MongoDB, the MCP servers) **skip** automatically when those services aren't available. `tests/test_system.py` is a manual integration harness — run it directly (`python tests/test_system.py`).

## Troubleshooting

- **"Failed to load MCP tools"** — run from the project root; ensure `src/mcp_server/kali.py` exists and the security tools are installed on the host.
- **"Failed to initialize agent"** — confirm Ollama is running (`ollama serve`), or set a cloud provider (`LLM_PROVIDER=openai`, plus the API key) in `.env`.
- **"MongoDB unavailable"** — CVA continues without session persistence; per-session file logs in `logs/` still record activity.
- **Knowledge base empty** — run `python scripts/ingest_kb.py` (or `make kb`) to build the local FTS5 index at `data/kb/cva_kb.sqlite3`; no external service is required.

## License

MIT License
