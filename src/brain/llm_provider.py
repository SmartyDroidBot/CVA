"""Multi-provider LLM factory — supports Ollama, OpenAI, Anthropic, Google."""

from langchain_ollama import ChatOllama
from src.config import settings


def get_llm(provider: str = None, model: str = None):
    """
    Create a ChatModel instance based on provider.
    
    Args:
        provider: Override settings.llm_provider
        model: Override the model name for the given provider
    
    Returns:
        A LangChain BaseChatModel instance
    """
    provider = (provider or settings.llm_provider).lower()
    
    if provider == "ollama":
        model_name = model or settings.ollama_model
        return ChatOllama(
            base_url=settings.ollama_base_url,
            model=model_name,
            temperature=0,
        )
    
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=model or settings.openai_model,
            temperature=0,
        )
    
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")
        return ChatAnthropic(
            api_key=settings.anthropic_api_key,
            model=model or settings.anthropic_model,
            temperature=0,
        )
    
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY not set in .env")
        return ChatGoogleGenerativeAI(
            google_api_key=settings.google_api_key,
            model=model or settings.google_model,
            temperature=0,
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use: ollama, openai, anthropic, google")
