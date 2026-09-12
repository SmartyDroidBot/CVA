# Customising CVA

CVA runs a single **planner/executor engine** (`src/engine.py`). Both modes use it:
copilot (interactive, `main.py`) calls `engine.answer()` once per message; autonomous
(`cva.py --auto`) calls `engine.run()`, which plans the engagement into a task graph
and executes each task with a bounded ReAct loop. There is no separate supervisor or
per-persona agent to configure — you tune the engine.

## Prompts

Three system prompts in `src/engine.py` shape behaviour:

| Constant | Used for |
|---|---|
| `_PLANNER_SYSTEM` | how the goal is decomposed into a task list (autonomous mode) |
| `_EXECUTOR_SYSTEM` | how each planned task is carried out |
| `_INTERACTIVE_SYSTEM` | the copilot persona for a single interactive turn |

Edit these to change methodology, tone, or output style. Keep them provider-neutral —
CVA is model-agnostic.

## Choosing / adding an LLM

Pick your provider and default model in `.env` (see the README's "Choosing your LLM").
Switch at runtime with `/model <provider:model>` or per run with `--model`.

To add a provider, extend `src/brain/llm_provider.py` with another `elif` branch and add
the dependency to `pyproject.toml`:

```python
elif provider == "my_provider":
    from langchain_myprovider import ChatMyProvider
    return ChatMyProvider(model=model or "default-model", temperature=0)
```

`get_llm()` is called on startup and whenever `/model` runs; the engine rebuilds its
bound tools on switch.

## Tools

The agent runs tools by name. Today the MCP servers expose `execute_shell_command`,
`read_local_file`, `execute_sandboxed_script`, `search_exploits`, and `examine_exploit`;
CVA also registers the in-process `search_knowledge_base` and `record_finding` tools.
Add or wire MCP servers in `config/mcp_servers.yaml` — see `docs/mcp_setup.md`.

## VAPT phase mapping

`src/tracker/task_tree.py` infers the current phase from the command that ran
(`infer_phase_from_command`) and from `TOOL_PHASE_MAP`. Add keywords/entries there when
you introduce new tooling so `/progress` and phase-scoped KB retrieval stay accurate.

## Knowledge base (pluggable)

Retrieval sits behind the `KnowledgeSource` interface (`src/knowledge/base.py`). The
default backend is `FTS5KnowledgeBase` (local SQLite full-text search). To add a vector
or hybrid backend, implement `KnowledgeSource` and construct the `KnowledgeService` with
it — no caller changes required. Build the index with `python scripts/ingest_kb.py`.

## Key files

| File | What to edit |
|---|---|
| `src/engine.py` | Planner / executor / interactive prompts and loop |
| `src/brain/llm_provider.py` | Add LLM providers |
| `src/tracker/task_tree.py` | Command → phase inference and tool→phase map |
| `src/knowledge/` | Knowledge backends (implement `KnowledgeSource`) |
| `config/mcp_servers.yaml` | MCP tool servers |
| `.env` | Default provider / model / keys |
