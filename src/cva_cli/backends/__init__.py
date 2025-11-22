"""Backend registry and factory"""

from typing import Dict, Type, Optional, List
from .base import LLMBackend, GenerationConfig, Message, ModelInfo
from .ollama import OllamaBackend
from .llamacpp import LlamaCppBackend


# Backend registry
_BACKENDS: Dict[str, Type[LLMBackend]] = {
    "ollama": OllamaBackend,
    "llama.cpp": LlamaCppBackend,
    "llamacpp": LlamaCppBackend,  # Alias
}


def register_backend(name: str, backend_class: Type[LLMBackend]):
    """
    Register a new backend.
    
    Args:
        name: Backend identifier
        backend_class: Backend class implementing LLMBackend
    """
    _BACKENDS[name.lower()] = backend_class


def get_backend(
    backend_name: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs
) -> LLMBackend:
    """
    Get a backend instance.
    
    Args:
        backend_name: Name of the backend
        model: Model to use
        base_url: Base URL for the backend API
        **kwargs: Additional backend-specific arguments
        
    Returns:
        Backend instance
        
    Raises:
        ValueError: If backend is not found
    """
    backend_name = backend_name.lower()
    
    if backend_name not in _BACKENDS:
        available = ", ".join(_BACKENDS.keys())
        raise ValueError(f"Unknown backend '{backend_name}'. Available: {available}")
    
    backend_class = _BACKENDS[backend_name]
    
    # Build arguments
    init_args = {}
    if model:
        init_args["model"] = model
    if base_url:
        init_args["base_url"] = base_url
    init_args.update(kwargs)
    
    return backend_class(**init_args)


def list_backends() -> List[str]:
    """
    List available backend names.
    
    Returns:
        List of backend names
    """
    return list(_BACKENDS.keys())


__all__ = [
    "LLMBackend",
    "GenerationConfig",
    "Message",
    "ModelInfo",
    "OllamaBackend",
    "LlamaCppBackend",
    "register_backend",
    "get_backend",
    "list_backends",
]
