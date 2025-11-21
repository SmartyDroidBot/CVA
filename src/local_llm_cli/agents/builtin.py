"""Built-in agent definitions - Import and register individual agents"""

from typing import List, Tuple, Dict
from .base import AgentConfig, SimpleAgent

# Import built-in agent modules
from .builtin_agents import general, coding, conversational


# Registry of built-in agents
BUILTIN_AGENTS: Dict[str, AgentConfig] = {}


def create_builtin_agent(agent_name: str) -> SimpleAgent:
    """
    Create a built-in agent by name.
    
    Args:
        agent_name: Name of the built-in agent
        
    Returns:
        Agent instance
        
    Raises:
        ValueError: If agent name is not found
    """
    agent_name = agent_name.lower()
    
    if agent_name not in BUILTIN_AGENTS:
        available = ", ".join(BUILTIN_AGENTS.keys())
        raise ValueError(f"Unknown agent '{agent_name}'. Available: {available}")
    
    config = BUILTIN_AGENTS[agent_name]
    return SimpleAgent(config, agent_type=agent_name)


def list_builtin_agents() -> List[Tuple[str, str]]:
    """
    List all built-in agents with descriptions.
    
    Returns:
        List of (name, description) tuples
    """
    return [(name, config.description) for name, config in BUILTIN_AGENTS.items()]
