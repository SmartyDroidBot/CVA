# Customising the CVA Agent

CVA uses a single LangGraph ReAct agent configured via `src/orchestrator.py`. This guide explains how to adjust its behaviour.

## Understanding the System Prompt

The agent's personality, VAPT methodology, and output style are controlled by `SYSTEM_PROMPT` in `src/orchestrator.py`:

```python
SYSTEM_PROMPT = """You are CVA (Cognitive VAPT Assistant)...
```

Edit this string to change how the agent reasons, what phases it follows, and what its output looks like.

## Adjusting via `config/agents.yaml`

`config/agents.yaml` is currently reserved for future multi-agent expansion. You can populate it with persona definitions; they are loaded by `config/config.yaml` but the main CVA loop uses the single system prompt in `orchestrator.py`.

Example `config/agents.yaml` entry:

```yaml
vapt:
  description: "Full VAPT operator"
  system_prompt: "You are a senior penetration tester..."
  temperature: 0.0
  max_tokens: 4096
```

## Switching Models at Runtime

Use the `/model` slash command inside CVA:

```
CVA ❯ /model ollama:llama3.2:3b
CVA ❯ /model openai:gpt-4o
CVA ❯ /model anthropic:claude-opus-4-5
CVA ❯ /model google:gemini-2.5-flash
```

Or set the default in `.env`:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b
```

## Tuning the LLM Factory

`src/brain/llm_provider.py` maps each provider to a LangChain `ChatModel`. To add a new provider, append an `elif` block:

```python
elif provider == "my_provider":
    from langchain_myprovider import ChatMyProvider
    return ChatMyProvider(model=model or "default-model", temperature=0)
```

No other changes are needed — the orchestrator calls `get_llm()` on startup and when `/model` is invoked.

## Adjusting VAPT Phase Mapping

`src/tracker/task_tree.py` maps tool names to VAPT phases. Add entries to `TOOL_PHASE_MAP` if you add new tools:

```python
TOOL_PHASE_MAP = {
    "nmap_scan": Phase.RECON,
    "my_new_tool": Phase.ENUM,   # add here
    ...
}
```

## Key Files

| File | What to Edit |
|---|---|
| `src/orchestrator.py` | System prompt, agent behaviour |
| `src/brain/llm_provider.py` | Add new LLM providers |
| `config/agents.yaml` | Persona definitions (future use) |
| `.env` | Default provider / model / API keys |
| `src/tracker/task_tree.py` | Tool → phase mapping |
