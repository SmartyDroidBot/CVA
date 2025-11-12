"""Agent system for managing different AI personas and behaviors"""

from .base import Agent, AgentConfig, SimpleAgent
from .builtin import (
    BUILTIN_AGENTS,
    create_builtin_agent,
    list_builtin_agents,
)
from .builtin_agents import (
    GENERAL_AGENT,
    CODING_AGENT,
    CONVERSATIONAL_AGENT,
)
from .registry import (
    AgentRegistry,
    get_agent,
    register_agent,
    register_config,
    list_agents,
    get_registry,
)

__all__ = [
    # Base classes
    "Agent",
    "AgentConfig",
    "SimpleAgent",
    
    # Built-in agents
    "BUILTIN_AGENTS",
    "create_builtin_agent",
    "list_builtin_agents",
    "GENERAL_AGENT",
    "CODING_AGENT",
    "CONVERSATIONAL_AGENT",
    
    # Registry
    "AgentRegistry",
    "get_agent",
    "register_agent",
    "register_config",
    "list_agents",
    "get_registry",
]
