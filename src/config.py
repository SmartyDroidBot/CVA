"""CVA Configuration — multi-provider LLM settings and service endpoints."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # LLM Provider
    llm_provider: str = Field(default="ollama", description="ollama | openai | anthropic | google")
    
    # Ollama
    ollama_model: str = Field(default="qwen3:8b")
    ollama_base_url: str = Field(default="http://localhost:11434")
    
    # Cloud API Keys (optional)
    openai_api_key: Optional[str] = Field(default=None)
    openai_model: str = Field(default="gpt-4o")
    anthropic_api_key: Optional[str] = Field(default=None)
    anthropic_model: str = Field(default="claude-sonnet-4-20250514")
    google_api_key: Optional[str] = Field(default=None)
    google_model: str = Field(default="gemini-2.5-flash")
    
    # Debug
    debug_mode: bool = Field(default=False, description="Show raw tool outputs")
    show_thinking: bool = Field(default=False, description="Show LLM reasoning (<think> blocks) in the terminal")
    show_tool_output: bool = Field(default=True, description="Show raw tool output after each tool call")
    require_approval: bool = Field(default=True, description="Ask for user approval before executing every tool call")
    
    # Services
    mongo_uri: str = Field(default="mongodb://localhost:27017")
    mongo_db: str = Field(default="cva_db")
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    
    # Sandbox
    sandbox_enabled: bool = Field(default=True)
    
    # Memory
    max_messages_before_summary: int = Field(default=20, description="Trigger summarizer after this many messages")
    
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton
settings = Settings()
