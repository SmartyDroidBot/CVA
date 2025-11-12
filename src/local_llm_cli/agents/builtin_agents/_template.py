"""
Template for creating custom agents

Copy this file to create your own custom agent. Place it in one of these locations:
1. src/local_llm_cli/agents/builtin_agents/ (to make it a built-in agent)
2. A custom agents directory (configure via config file - coming in Phase 4)

Example: custom_agents/my_agent.py
"""

from ..base import AgentConfig

# Define your agent configuration
AGENT_CONFIG = AgentConfig(
    name="example",  # Unique name for your agent (lowercase, no spaces)
    description="Brief description of what your agent does",
    
    # System prompt defines the agent's behavior and personality
    system_prompt="""You are [describe the agent's role and personality].

Your primary responsibilities:
- [Responsibility 1]
- [Responsibility 2]
- [Responsibility 3]

Your communication style:
- [Style characteristic 1]
- [Style characteristic 2]

Guidelines:
- [Guideline 1]
- [Guideline 2]""",
    
    # Temperature controls randomness (0.0 = deterministic, 2.0 = very creative)
    # - 0.0-0.3: Focused, deterministic (good for code, analysis)
    # - 0.4-0.7: Balanced (good for general use)
    # - 0.8-1.2: Creative (good for writing, brainstorming)
    temperature=0.7,
    
    # Top-p sampling (0.0-1.0) - alternative to temperature
    # Lower values = more focused, higher = more diverse
    top_p=0.9,
    
    # Top-k sampling - limits to top k tokens
    top_k=40,
    
    # Maximum tokens to generate (None = model default)
    max_tokens=None,
    
    # Preferred model for this agent (None = use user's choice)
    # Examples: "codellama", "mistral", "llama2"
    preferred_model=None,
    
    # Tools this agent can use (will be implemented in Phase 3)
    tools=[],
    
    # Additional metadata (optional)
    metadata={
        "author": "Your Name",
        "version": "1.0",
        "tags": ["category1", "category2"],
    }
)

# To register this agent as a built-in:
# 1. Save this file as src/local_llm_cli/agents/builtin_agents/your_agent_name.py
# 2. Import it in src/local_llm_cli/agents/builtin_agents/__init__.py
# 3. Add it to BUILTIN_AGENTS in src/local_llm_cli/agents/builtin.py

# Example registration in builtin.py:
# from .builtin_agents import your_agent_name
# BUILTIN_AGENTS = {
#     ...
#     "your_agent": your_agent_name.AGENT_CONFIG,
# }
