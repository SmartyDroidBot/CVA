"""Multi-provider LLM factory — supports Ollama, OpenAI, Anthropic, Google."""

from langchain_ollama import ChatOllama
from src.config import settings


def check_llm_ready(provider: str = None) -> tuple[bool, str]:
    """Cheap reachability/config check for the configured LLM.

    Returns (ok, message). Callers should fail fast when ok is False instead of
    running an engagement against an unreachable model (which otherwise fails
    silently, one call at a time, and yields an empty report).
    """
    provider = (provider or settings.llm_provider).lower()

    if provider == "ollama":
        base = settings.ollama_base_url.rstrip("/")
        model = settings.ollama_model
        try:
            import httpx
            resp = httpx.get(f"{base}/api/tags", timeout=4.0)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
        except Exception as e:
            return (False,
                    f"LLM not reachable: Ollama at {base} ({e}).\n"
                    f"  - Is Ollama running?  (ollama serve)\n"
                    f"  - In WSL the Windows host is NOT localhost. Enable WSL mirrored\n"
                    f"    networking, or set OLLAMA_BASE_URL to the host IP in .env.\n"
                    f"    See README: 'Running the LLM from WSL'.")
        if model and not any(
            n == model or n.split(":")[0] == model.split(":")[0] for n in names
        ):
            return (False,
                    f"Ollama is reachable at {base}, but model '{model}' is not pulled.\n"
                    f"  - Pull it:  ollama pull {model}")
        return (True, f"Ollama ready at {base} ({model}).")

    if provider in ("openai", "anthropic", "google"):
        key = getattr(settings, f"{provider}_api_key", "")
        if not key:
            return (False,
                    f"Provider '{provider}' selected but {provider.upper()}_API_KEY "
                    f"is not set in .env.")
        return (True, f"Provider '{provider}' configured (API key present).")

    return (False,
            f"Unknown LLM provider '{provider}' — use: ollama | openai | anthropic | google.")


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
