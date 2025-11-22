"""Agent system for managing different AI personas and behaviors"""

from .base import Agent, AgentConfig, SimpleAgent
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
    
    # Registry
    "AgentRegistry",
    "get_agent",
    "register_agent",
    "register_config",
    "list_agents",
    "get_registry",
]
