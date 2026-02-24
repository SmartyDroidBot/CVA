"""Tests for CVA Config module."""

import os
import pytest
from src.config import Settings


def test_default_settings():
    """Test default settings load correctly."""
    s = Settings()
    assert s.llm_provider == "ollama"
    assert s.ollama_model == "qwen3:8b"
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.debug_mode is False
    assert s.mongo_uri == "mongodb://localhost:27017"
    assert s.qdrant_host == "localhost"
    assert s.qdrant_port == 6333
    assert s.sandbox_enabled is True
    assert s.max_messages_before_summary == 20


def test_provider_names():
    """Test supported provider names."""
    valid_providers = ["ollama", "openai", "anthropic", "google"]
    for p in valid_providers:
        s = Settings(llm_provider=p)
        assert s.llm_provider == p


def test_debug_toggle():
    """Test debug mode can be toggled."""
    s = Settings(debug_mode=True)
    assert s.debug_mode is True
    s2 = Settings(debug_mode=False)
    assert s2.debug_mode is False


def test_env_override(monkeypatch):
    """Test environment variables override defaults."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.setenv("DEBUG_MODE", "true")
    
    s = Settings()
    assert s.llm_provider == "openai"
    assert s.ollama_model == "llama3.1:8b"
    assert s.debug_mode is True
