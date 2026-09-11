"""CVA Configuration — centralised Pydantic settings loaded from .env.

Changes from v2:
- Removed sandbox_enabled (was never enforced — false security)
- Added agent_mode: supervisor or single
- Added guardrails_enabled
- Added auto_session: auto-creates session at startup
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All CVA settings, loaded from .env or environment variables."""

    # ── LLM Provider ──────────────────────────────────────────────────────────
    llm_provider: str = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Google
    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"

    # ── Agent Architecture ────────────────────────────────────────────────────
    agent_mode: str = "supervisor"  # "supervisor" or "single"

    # ── Guardrails ────────────────────────────────────────────────────────────
    guardrails_enabled: bool = True
    guardrail_threshold: float = 0.5  # risk score above which input is blocked

    # ── Session / Memory ──────────────────────────────────────────────────────
    auto_session: bool = True  # auto-create a session at startup
    max_messages_before_summary: int = 30

    # MongoDB (optional — falls back to in-memory if unavailable)
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "cva"

    # ── Knowledge Base ────────────────────────────────────────────────────────
    # Retrieval backend (pluggable). "fts5" = local SQLite full-text search.
    kb_backend: str = "fts5"
    kb_db_path: str = "data/kb/cva_kb.sqlite3"

    # ── UI / Debug ────────────────────────────────────────────────────────────
    debug_mode: bool = False
    show_thinking: bool = False
    show_tool_output: bool = False
    require_approval: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
