# Quick Setup Guide for Local LLM CLI

## Windows Setup (Step-by-Step)

### 1. Install uv

```powershell
# Using PowerShell
irm https://astral.sh/uv/install.ps1 | iex
```

Or download from [astral.sh/uv](https://astral.sh/uv)

### 2. Install Dependencies

```powershell
cd d:\Projects\CVA
uv sync
```

### 3. Install Ollama (Easiest Option)

1. Download Ollama from [ollama.ai](https://ollama.ai/download)
2. Run the installer
3. Open PowerShell and install a model:

```powershell
# Install a fast, general-purpose model
ollama pull llama2

# Or install Mistral (better quality)
ollama pull mistral

# Or install a coding model
ollama pull codellama
```

4. Verify installation:
```powershell
ollama list
```

### 4. Initialize and Test the CLI

```powershell
# Write config/config.yaml (plus agents.yaml & mcp_servers.yaml)
uv run llm --init-config

# Test basic prompt
uv run llm "Hello, who are you?"

# Test chat mode
uv run llm --chat
```

## Quick Start Examples

### Example 1: Ask a Question
```powershell
uv run llm "What is the difference between Python and JavaScript?"
```

### Example 2: Start a Conversation
```powershell
uv run llm --chat
```
Then type your questions. Type `exit` to quit.

### Example 3: Get Help with Code
```powershell
uv run llm "Write a Python function that calculates fibonacci numbers"
```

### Example 4: Summarize a File
```powershell
Get-Content README.md | uv run llm
```

## Making it Easier to Use

### Option 1: Install Globally (Recommended)

```powershell
cd d:\Projects\CVA
uv pip install -e .
```

Now the `llm` command is available everywhere:
```powershell
llm "What is AI?"
llm --chat
```

### Option 2: Add Alias to PowerShell Profile

Edit your PowerShell profile:
```powershell
notepad $PROFILE
```

Add these functions:
```powershell
function llm { uv run --directory d:\Projects\CVA llm $args }
function chat { uv run --directory d:\Projects\CVA llm --chat $args }
```

Save and reload:
```powershell
. $PROFILE
```

Now you can use:
```powershell
llm "What is AI?"
chat
```

## Recommended Models by Use Case

### General Chat
- `llama2` (7B) - Fast, good for most tasks
- `mistral` (7B) - Higher quality responses
- `neural-chat` (7B) - Great for conversations

### Coding
- `codellama` (7B, 13B, 34B) - Best for code
- `deepseek-coder` - Excellent code understanding

### Fast & Light
- `phi` (2.7B) - Very fast, smaller
- `tinyllama` (1.1B) - Extremely fast

### Advanced
- `llama2:70b` - Highest quality (requires 64GB+ RAM)
- `mixtral` (8x7B) - Excellent quality

Install any model:
```powershell
ollama pull <model-name>
```

## Troubleshooting

### Issue: "Cannot connect to Ollama"
**Solution**: Make sure Ollama is running.
```powershell
ollama serve
```

### Issue: "Model not found"
**Solution**: Pull the model first, then list available ones.
```powershell
ollama pull llama2
uv run llm --list-models
```

### Issue: Slow responses
**Solution**: Use a smaller model or override per-call settings.
```powershell
ollama pull phi
uv run llm --model phi "Answer quickly"
```

## Next Steps

1. Try different models to find what works best
2. Set up aliases for faster access
3. Enable MCP servers and run `uv run llm --list-tools`
4. Explore chat mode for multi-turn workflows

Enjoy your local, private AI assistant!
