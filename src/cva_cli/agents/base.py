"""Base agent class and interfaces"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from ..backends.base import GenerationConfig


@dataclass
class AgentConfig:
    """Configuration for an agent"""
    name: str
    description: str
    system_prompt: str
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: Optional[int] = None
    preferred_model: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_generation_config(self) -> GenerationConfig:
        """Convert to GenerationConfig for backend"""
        return GenerationConfig(
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            max_tokens=self.max_tokens,
            stream=True
        )


class Agent(ABC):
    """Base class for AI agents with specific behaviors"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.name = config.name
        self.description = config.description
        self.system_prompt = config.system_prompt
    
    def get_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Get the system prompt, optionally with context injection.
        
        Args:
            context: Optional context to inject into the prompt
            
        Returns:
            Formatted system prompt
        """
        if context:
            return self._format_prompt_with_context(self.system_prompt, context)
        return self.system_prompt
    
    def _format_prompt_with_context(self, prompt: str, context: Dict[str, Any]) -> str:
        """Format prompt with context variables"""
        try:
            return prompt.format(**context)
        except KeyError:
            # If formatting fails, return original prompt
            return prompt
    
    def get_generation_config(self) -> GenerationConfig:
        """Get generation configuration for this agent"""
        return self.config.to_generation_config()
    
    def get_preferred_model(self) -> Optional[str]:
        """Get preferred model for this agent"""
        return self.config.preferred_model
    
    def get_tools(self) -> List[str]:
        """Get list of tool names this agent can use"""
        return self.config.tools.copy()
    
    def preprocess_input(self, user_input: str) -> str:
        """
        Preprocess user input before sending to LLM.
        Override for custom preprocessing.
        
        Args:
            user_input: Raw user input
            
        Returns:
            Preprocessed input
        """
        return user_input
    
    def postprocess_output(self, llm_output: str) -> str:
        """
        Postprocess LLM output before returning to user.
        Override for custom postprocessing.
        
        Args:
            llm_output: Raw LLM output
            
        Returns:
            Processed output
        """
        return llm_output
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """Return the type/category of this agent"""
        pass
    
    def __repr__(self) -> str:
        return f"Agent(name='{self.name}', type='{self.get_agent_type()}')"


class SimpleAgent(Agent):
    """Simple agent implementation with just a system prompt"""
    
    def __init__(self, config: AgentConfig, agent_type: str = "general"):
        super().__init__(config)
        self._agent_type = agent_type
    
    def get_agent_type(self) -> str:
        return self._agent_type
