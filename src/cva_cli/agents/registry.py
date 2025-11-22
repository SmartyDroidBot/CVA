"""Agent registry for managing and discovering agents"""

from typing import Dict, Optional, List, Tuple
from .base import Agent, AgentConfig, SimpleAgent


class AgentRegistry:
    """Registry for managing agents"""
    
    def __init__(self):
        self._agents: Dict[str, Agent] = {}
        self._configs: Dict[str, AgentConfig] = {}
    
    def register_agent(self, agent: Agent):
        """
        Register a custom agent.
        
        Args:
            agent: Agent instance to register
        """
        self._agents[agent.name] = agent
        self._configs[agent.name] = agent.config
    
    def register_config(self, config: AgentConfig):
        """
        Register an agent configuration.
        
        Args:
            config: Agent configuration
        """
        self._configs[config.name] = config
    
    def get_agent(self, name: str) -> Agent:
        """
        Get an agent by name.
        
        Args:
            name: Agent name
            
        Returns:
            Agent instance
            
        Raises:
            ValueError: If agent not found
        """
        name = name.lower()
        
        # Check if already instantiated
        if name in self._agents:
            return self._agents[name]
        
        # Check if config exists
        if name in self._configs:
            config = self._configs[name]
            agent = SimpleAgent(config, agent_type=name)
            self._agents[name] = agent
            return agent
        
        available = ", ".join(self.list_agent_names())
        raise ValueError(f"Unknown agent '{name}'. Available: {available}")
    
    def get_config(self, name: str) -> Optional[AgentConfig]:
        """
        Get agent configuration by name.
        
        Args:
            name: Agent name
            
        Returns:
            Agent configuration or None
        """
        return self._configs.get(name.lower())
    
    def list_agent_names(self) -> List[str]:
        """
        List all available agent names.
        
        Returns:
            List of agent names
        """
        return list(self._configs.keys())
    
    def list_agents(self) -> List[Tuple[str, str]]:
        """
        List all agents with descriptions.
        
        Returns:
            List of (name, description) tuples
        """
        return [(name, config.description) for name, config in self._configs.items()]
    
    def agent_exists(self, name: str) -> bool:
        """
        Check if an agent exists.
        
        Args:
            name: Agent name
            
        Returns:
            True if agent exists
        """
        return name.lower() in self._configs
    
    def remove_agent(self, name: str):
        """
        Remove a custom agent.
        
        Args:
            name: Agent name
        """
        name = name.lower()
        
        self._agents.pop(name, None)
        self._configs.pop(name, None)


# Global registry instance
_global_registry = AgentRegistry()


def get_agent(name: str) -> Agent:
    """Get an agent from the global registry"""
    return _global_registry.get_agent(name)


def register_agent(agent: Agent):
    """Register an agent in the global registry"""
    _global_registry.register_agent(agent)


def register_config(config: AgentConfig):
    """Register an agent config in the global registry"""
    _global_registry.register_config(config)


def list_agents() -> List[Tuple[str, str]]:
    """List all available agents"""
    return _global_registry.list_agents()


def get_registry() -> AgentRegistry:
    """Get the global agent registry"""
    return _global_registry
