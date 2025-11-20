# Creating Custom Agents

This guide shows you how to create custom agents for the Local LLM CLI.

## Quick Start

1. Copy the template:
   ```powershell
   cp src/local_llm_cli/agents/builtin_agents/_template.py src/local_llm_cli/agents/builtin_agents/my_agent.py
   ```

2. Edit the configuration in `my_agent.py`:
   - Change the `name`
   - Update the `description`
   - Customize the `system_prompt`
   - Adjust `temperature` and other parameters

3. Register your agent in `src/local_llm_cli/agents/builtin_agents/__init__.py`:
   ```python
   from .my_agent import AGENT_CONFIG as MY_AGENT
   
   __all__ = [
       # ... existing agents
       "MY_AGENT",
   ]
   ```

4. Add to the registry in `src/local_llm_cli/agents/builtin.py`:
   ```python
   from .builtin_agents import my_agent
   
   BUILTIN_AGENTS: Dict[str, AgentConfig] = {
       # ... existing agents
       "my_agent": my_agent.AGENT_CONFIG,
   }
   ```

5. Test your agent:
     ```powershell
     uv run llm --agent my_agent "Test prompt"
     ```

## Config-Only Tweaks

Need to adjust temperature, `max_tokens`, or the system prompt without writing Python? Edit `config/agents.yaml`:

```yaml
general:
    temperature: 0.6
    system_prompt: "One-line override"
my_agent:
    temperature: 0.25
    max_tokens: 2048
```

These values are validated by Pydantic and automatically applied every time you call the agent.

## Agent Configuration Options

### name (required)
Unique identifier for your agent. Use lowercase with underscores.
```python
name="data_analyst"
```

### description (required)
Brief description shown in `--list-agents`.
```python
description="Data analysis and visualization specialist"
```

### system_prompt (required)
The personality and behavior of your agent. This is the most important field!

**Tips for writing system prompts:**
- Be specific about the agent's role
- Define the communication style
- Set clear guidelines for behavior
- Include examples if needed
- Keep it focused on one main purpose

```python
system_prompt="""You are a data analysis expert specializing in Python and pandas.

Your approach:
- Ask clarifying questions about the data
- Suggest appropriate analysis techniques
- Provide complete, runnable code examples
- Explain statistical concepts clearly

Always consider data quality and edge cases."""
```

### temperature (optional, default: 0.7)
Controls randomness in responses:
- **0.0-0.3**: Very focused and deterministic (code, analysis, factual)
- **0.4-0.7**: Balanced (general use)
- **0.8-1.2**: Creative and varied (writing, brainstorming)
- **1.3-2.0**: Very creative, sometimes unpredictable

```python
temperature=0.2  # For a precise, factual agent
```

### preferred_model (optional)
Suggest a specific model for this agent:
```python
preferred_model="codellama"  # For coding agents
preferred_model="mistral"    # For general high-quality
```

### tools (optional, list)
Tools this agent can use (Phase 3 feature):
```python
tools=["file_reader", "calculator", "web_search"]
```

### Other options
```python
top_p=0.9          # Alternative to temperature
top_k=40           # Limits token selection
max_tokens=2000    # Maximum response length
metadata={}        # Custom metadata
```

## Example: Creating a Data Analyst Agent

**File: `src/local_llm_cli/agents/builtin_agents/data_analyst.py`**

```python
from ..base import AgentConfig

AGENT_CONFIG = AgentConfig(
    name="data_analyst",
    description="Data analysis specialist using Python and pandas",
    system_prompt="""You are an expert data analyst specializing in Python, pandas, and statistical analysis.

Your workflow:
1. Understand the data and the question
2. Suggest appropriate analysis approaches
3. Provide complete, tested code examples
4. Explain results and insights clearly
5. Recommend visualizations when helpful

Code style:
- Use pandas best practices
- Include error handling
- Add comments for complex operations
- Provide example outputs

Always consider data quality, missing values, and edge cases.""",
    temperature=0.3,
    preferred_model="codellama",
    tools=["file_reader"],
    metadata={
        "author": "Your Name",
        "version": "1.0",
        "specialties": ["pandas", "statistics", "visualization"],
    }
)
```

**Register in `__init__.py`:**
```python
from .data_analyst import AGENT_CONFIG as DATA_ANALYST_AGENT

__all__ = [
    "GENERAL_AGENT",
    "CODING_AGENT",
    "CONVERSATIONAL_AGENT",
    "DATA_ANALYST_AGENT",  # Add this
]
```

**Register in `builtin.py`:**
```python
from .builtin_agents import data_analyst

BUILTIN_AGENTS: Dict[str, AgentConfig] = {
    "general": general.AGENT_CONFIG,
    "coding": coding.AGENT_CONFIG,
    "conversational": conversational.AGENT_CONFIG,
    "data_analyst": data_analyst.AGENT_CONFIG,  # Add this
}
```

## Agent Examples by Use Case

### Technical Writer Agent
```python
AGENT_CONFIG = AgentConfig(
    name="tech_writer",
    description="Technical documentation specialist",
    system_prompt="""You write clear, accurate technical documentation.

Writing principles:
- Use active voice and present tense
- Structure content hierarchically
- Include code examples
- Write for the target audience
- Use consistent terminology""",
    temperature=0.3,
)
```

### Creative Writer Agent
```python
AGENT_CONFIG = AgentConfig(
    name="novelist",
    description="Creative fiction writing assistant",
    system_prompt="""You are a creative fiction writing assistant.

Your strengths:
- Character development
- Plot structuring
- Vivid descriptions
- Dialogue writing
- World-building

Help users develop compelling stories with rich detail.""",
    temperature=0.9,
    top_p=0.95,
)
```

### Teaching Agent
```python
AGENT_CONFIG = AgentConfig(
    name="tutor",
    description="Patient teacher for any subject",
    system_prompt="""You are a patient, encouraging tutor.

Teaching approach:
- Start simple, build up complexity
- Use analogies and examples
- Check understanding frequently
- Encourage questions
- Provide practice exercises
- Adapt to the student's level""",
    temperature=0.6,
)
```

## Tips for Great Agents

1. **Single Purpose**: Each agent should excel at one thing
2. **Clear Instructions**: The system prompt should be explicit
3. **Right Temperature**: Match the temperature to the task
4. **Test Thoroughly**: Try edge cases and different prompts
5. **Iterate**: Refine based on actual usage

## Advanced: Custom Agent Classes

For complex behavior, extend the `Agent` class:

```python
from ..base import Agent, AgentConfig

class DataAnalystAgent(Agent):
    def preprocess_input(self, user_input: str) -> str:
        # Add data context or formatting
        if "analyze" in user_input.lower():
            return f"Data Analysis Request: {user_input}\nPlease provide step-by-step analysis."
        return user_input
    
    def postprocess_output(self, llm_output: str) -> str:
        # Clean up or format the output
        return llm_output.strip()
    
    def get_agent_type(self) -> str:
        return "data_analyst"

# Use it
config = AgentConfig(name="data_analyst", ...)
agent = DataAnalystAgent(config)
```

Then register it directly:
```python
from local_llm_cli.agents import register_agent
register_agent(agent)
```

## Testing Your Agent

```powershell
# Single prompt
uv run llm --agent my_agent "Test this functionality"

# Interactive chat
uv run llm --chat --agent my_agent

# Compare with another agent
uv run llm --agent general "Same question"
uv run llm --agent my_agent "Same question"
```

## Sharing Your Agents

To share your custom agent:
1. Create a gist or repo with your agent file
2. Document the installation process
3. Include example usage

Users can then copy your agent file into their `builtin_agents/` directory!
