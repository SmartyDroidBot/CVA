"""Tests for Brain module — LLM provider factory and thinking parser."""

import pytest
from src.brain.thinking import parse_thinking, strip_thinking, ThinkingResult


class TestThinkingParser:
    """Tests for thinking block parsing."""
    
    def test_no_thinking_blocks(self):
        """Plain text should pass through unchanged."""
        text = "This is a normal response without any thinking."
        result = parse_thinking(text)
        assert result.thinking is None
        assert result.content == text
    
    def test_think_tags(self):
        """Qwen3-style <think> tags should be extracted."""
        text = "<think>I need to analyze the ports.</think>Here are the open ports: 80, 443"
        result = parse_thinking(text)
        assert result.thinking == "I need to analyze the ports."
        assert result.content == "Here are the open ports: 80, 443"
    
    def test_thinking_tags(self):
        """<thinking> tags should be extracted."""
        text = "<thinking>Let me reason about this.</thinking>The answer is 42."
        result = parse_thinking(text)
        assert result.thinking == "Let me reason about this."
        assert result.content == "The answer is 42."
    
    def test_reasoning_tags(self):
        """<reasoning> tags should be extracted."""
        text = "<reasoning>Step 1: scan ports</reasoning>I suggest running nmap."
        result = parse_thinking(text)
        assert result.thinking == "Step 1: scan ports"
        assert result.content == "I suggest running nmap."
    
    def test_multiline_thinking(self):
        """Multi-line thinking blocks should be captured."""
        text = "<think>\nLine 1\nLine 2\nLine 3\n</think>Response here"
        result = parse_thinking(text)
        assert "Line 1" in result.thinking
        assert "Line 3" in result.thinking
        assert result.content == "Response here"
    
    def test_multiple_think_blocks(self):
        """Multiple thinking blocks should all be extracted."""
        text = "<think>First thought</think>Middle text<think>Second thought</think>Final text"
        result = parse_thinking(text)
        assert "First thought" in result.thinking
        assert "Second thought" in result.thinking
        assert "Middle text" in result.content
        assert "Final text" in result.content
    
    def test_empty_input(self):
        """Empty input should return empty result."""
        result = parse_thinking("")
        assert result.thinking is None
        assert result.content == ""
    
    def test_strip_thinking_helper(self):
        """strip_thinking should return only content."""
        text = "<think>Hidden reasoning</think>Visible response"
        assert strip_thinking(text) == "Visible response"
    
    def test_deepseek_thought_tags(self):
        """DeepSeek-style thought tags should be extracted."""
        text = "<|begin_of_thought|>Deep reasoning here<|end_of_thought|>The conclusion."
        result = parse_thinking(text)
        assert result.thinking == "Deep reasoning here"
        assert result.content == "The conclusion."


class TestLLMProvider:
    """Tests for LLM provider factory — only tests that don't require API keys."""
    
    def test_invalid_provider_raises(self):
        """Unknown provider should raise ValueError."""
        from src.brain.llm_provider import get_llm
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm("nonexistent_provider")
    
    def test_ollama_provider_returns_chat_model(self):
        """Ollama provider should return a ChatOllama instance."""
        from src.brain.llm_provider import get_llm
        llm = get_llm("ollama", "qwen3:8b")
        assert llm is not None
        assert hasattr(llm, "invoke")
    
    def test_openai_without_key_raises(self):
        """OpenAI without API key should raise ValueError."""
        from src.brain.llm_provider import get_llm
        from src.config import settings
        original = settings.openai_api_key
        settings.openai_api_key = None
        try:
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                get_llm("openai")
        finally:
            settings.openai_api_key = original


class TestLLMPreflight:
    """Tests for check_llm_ready — the startup reachability check."""

    def test_ollama_unreachable_is_not_ready(self, monkeypatch):
        """A dead Ollama endpoint reports not-ready with an actionable message."""
        from src.brain import llm_provider
        from src.config import settings
        # Port 1 is unused → immediate connection refusal (the Errno 111 case).
        monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:1")
        ok, msg = llm_provider.check_llm_ready("ollama")
        assert ok is False
        assert "not reachable" in msg.lower()
        assert "WSL" in msg   # includes the WSL hint

    def test_cloud_without_key_is_not_ready(self, monkeypatch):
        from src.brain import llm_provider
        from src.config import settings
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        ok, msg = llm_provider.check_llm_ready("anthropic")
        assert ok is False
        assert "ANTHROPIC_API_KEY" in msg

    def test_cloud_with_key_is_ready(self, monkeypatch):
        from src.brain import llm_provider
        from src.config import settings
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        ok, msg = llm_provider.check_llm_ready("openai")
        assert ok is True

    def test_unknown_provider_is_not_ready(self):
        from src.brain import llm_provider
        ok, msg = llm_provider.check_llm_ready("bogus")
        assert ok is False
