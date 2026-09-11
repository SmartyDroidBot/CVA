# Customising CVA's Agents

CVA runs a **multi-agent supervisor** by default (`agent_mode="supervisor"`): a routing node in `src/orchestrator.py` picks one specialist per turn, and each specialist is a persona defined in `src/agents/`. A legacy single-agent mode (`agent_mode="single"`) is also available via `/mode single` or `--mode single`.

## Specialist personas

Each persona is a Python module in `src/agents/` that builds an `AgentDef` and registers it:

| File | Specialist |
|---|---|
| `src/agents/recon.py` | Reconnaissance & enumeration |
| `src/agents/exploit.py` | Exploitation |
| `src/agents/post_exploit.py` | Post-exploitation |
| `src/agents/reporter.py` | Reporting |
| `src/agents/registry.py` | `AgentDef`, `register_agent`, `list_agents` |

A persona looks like this:

```python
from src.agents.registry import AgentDef, register_agent

MY_TOOLS = {"execute_shell_command", "read_local_file"}  # tool names to allow

def _filter(tools):
    return [t for t in tools if t.name in MY_TOOLS]

SYSTEM_PROMPT = """You are the ... specialist. ..."""

my_agent = AgentDef(
    name="my_agent",
    description="What this specialist does (shown to the supervisor router).",
    system_prompt=SYSTEM_PROMPT,
    tool_filter=_filter,
)
register_agent(my_agent)
```

Registration happens on import; `src/agents/registry.py` imports the persona modules so they self-register. To add a specialist, create the module and add it to the registry's import list, then update the supervisor routing prompt in `src/orchestrator.py` (`_SUPERVISOR_TEMPLATE`) so the router knows when to pick it.

> **Tool filters must reference tools that actually exist.** The MCP servers currently expose `execute_shell_command`, `read_local_file`, `execute_sandboxed_script`, `search_exploits`, and `examine_exploit` (see `docs/mcp_setup.md`). A filter that matches no real tool name falls back to the full tool set.

## The single-agent prompt

In `single` mode the whole methodology is driven by one prompt: `Orchestrator._unified_prompt()` in `src/orchestrator.py`. Edit that method to change the single-agent persona.

## Switching models at runtime

```
CVA ❯ /model ollama:llama3.2:3b
CVA ❯ /model openai:gpt-4o
CVA ❯ /model anthropic:claude-sonnet-4-20250514
CVA ❯ /model google:gemini-2.5-flash
```

Or set the default in `.env` (`LLM_PROVIDER`, `OLLAMA_MODEL`, and provider API keys). A capable cloud model is recommended for reliable tool-calling; small local models can loop or emit malformed tool calls.

## Adding an LLM provider

`src/brain/llm_provider.py` maps each provider to a LangChain chat model. Append an `elif` block and add the dependency to `pyproject.toml`:

```python
elif provider == "my_provider":
    from langchain_myprovider import ChatMyProvider
    return ChatMyProvider(model=model or "default-model", temperature=0)
```

`get_llm()` is called on startup and whenever `/model` is used.

## VAPT phase mapping

`src/tracker/task_tree.py` maps tool names to VAPT phases via `TOOL_PHASE_MAP`. Because most tooling runs through `execute_shell_command`, the tracker also keeps the current phase sticky between recognised tools. Add entries when you introduce dedicated tools.

## Key files

| File | What to edit |
|---|---|
| `src/agents/*.py` | Specialist personas (prompt + tool filter) |
| `src/orchestrator.py` | Supervisor routing prompt; single-agent prompt |
| `src/brain/llm_provider.py` | Add LLM providers |
| `src/tracker/task_tree.py` | Tool → phase mapping |
| `.env` | Default provider / model / API keys |
