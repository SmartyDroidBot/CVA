"""Base backend interface for LLM providers"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Iterator, Any
from dataclasses import dataclass


@dataclass
class Message:
    """Represents a chat message"""
    role: str  # 'user', 'assistant', 'system'
    content: str


@dataclass
class ModelInfo:
    """Information about a model"""
    name: str
    size: Optional[int] = None  # Size in bytes
    description: Optional[str] = None
    modified: Optional[str] = None


@dataclass
class GenerationConfig:
    """Configuration for text generation"""
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    stream: bool = True
    timeout: int = 120


@dataclass
class GenerationResponse:
    """Response from text generation"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None  # Token usage statistics
    finish_reason: Optional[str] = None  # 'stop', 'length', etc.


class LLMBackend(ABC):
    """Abstract base class for LLM backends"""
    
    def __init__(self, model: str, base_url: str, **kwargs):
        self.model = model
        self.base_url = base_url
        self.config = kwargs
        self.conversation_history: List[Message] = []
    
    @abstractmethod
    def generate(
        self,
        model: str,
        messages: List[Message],
        config: Optional[GenerationConfig] = None
    ) -> GenerationResponse:
        """
        Generate a response from messages.
        
        Args:
            model: The model name to use
            messages: List of conversation messages
            config: Generation configuration
            
        Returns:
            GenerationResponse with content and metadata
        """
        pass
    
    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Iterator[str]:
        """
        Generate a streaming response from a prompt.
        
        Args:
            prompt: The input prompt
            system: Optional system prompt
            config: Generation configuration
            
        Yields:
            Chunks of generated text
        """
        pass
    
    @abstractmethod
    def chat(
        self,
        message: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> str:
        """
        Send a chat message with conversation history.
        
        Args:
            message: The chat message
            system: Optional system prompt
            config: Generation configuration
            
        Returns:
            Assistant's response
        """
        pass
    
    @abstractmethod
    def chat_stream(
        self,
        message: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Iterator[str]:
        """
        Send a chat message with streaming response.
        
        Args:
            message: The chat message
            system: Optional system prompt
            config: Generation configuration
            
        Yields:
            Chunks of assistant's response
        """
        pass
    
    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """
        List available models.
        
        Returns:
            List of available models
        """
        pass
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history"""
        self.conversation_history.append(Message(role=role, content=content))
    
    def get_history(self) -> List[Message]:
        """Get conversation history"""
        return self.conversation_history.copy()
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the backend is available and healthy.
        
        Returns:
            True if backend is available, False otherwise
        """
        pass
    
    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return the name of the backend"""
        pass
