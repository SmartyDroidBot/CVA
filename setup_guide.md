# CVA — Quick Setup Guide

## 1. Install uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

## 2. Install Python Dependencies

```bash
cd CVA
uv sync
```

> `uv sync` reads `pyproject.toml` and `uv.lock` to create the virtual environment in `.venv/`.

## 3. Install Ollama and a Model

Download Ollama from [ollama.ai](https://ollama.ai) then pull a model:

```bash
ollama pull qwen3:8b      # recommended default
# or
ollama pull llama3.2:3b   # lighter option
```

Verify Ollama is running:
```bash
ollama list
```

## 4. Configure the Environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum set `OLLAMA_MODEL` to the model you pulled. See `.env.example` for all options including cloud LLM keys and optional service endpoints.

## 5. (Optional) Start Supporting Services

### MongoDB — for session persistence

```bash
docker compose up -d mongodb
# or: mongod --dbpath /data/db
```

### Knowledge base — local FTS5 index (no service needed)

```bash
python scripts/ingest_kb.py     # builds data/kb/cva_kb.sqlite3
```

Without MongoDB, CVA still starts — sessions simply aren't persisted (file logs still work). The knowledge base is a local SQLite FTS5 index, so it needs no external service.

## 6. Run CVA

```bash
python main.py
```

You should see the CVA banner and the `CVA ❯` prompt. Type `/help` for commands.

---

## Using a Cloud LLM Instead of Ollama

Edit `.env`:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Supported providers: `ollama`, `openai`, `anthropic`, `google`.

---

## Common Issues

| Issue | Fix |
|---|---|
| `Failed to initialize agent` | Start Ollama (`ollama serve`) or set a cloud provider |
| `Failed to load MCP tools` | Run from the project root; ensure `src/mcp_server/kali.py` is present |
| `MongoDB not available` | Normal — sessions are in-memory. Start MongoDB for persistence |
| Missing security tool (nmap, etc.) | Install the tool on the host system |

---

## Project Layout

```
CVA/
├── main.py             # Start here — the TUI entry point
├── src/                # Application source
├── config/             # YAML configuration files
├── docs/               # Extended documentation
├── tests/              # Test suite
├── .env.example        # Environment variable template
└── pyproject.toml      # Dependencies
```

See `README.md` for the full architecture diagram and command reference.
