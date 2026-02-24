"""Thinking block parser — strips <think> tags from reasoning models."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ThinkingResult:
    """Parsed LLM output with thinking separated from content."""
    thinking: Optional[str]
    content: str


# Patterns for various thinking tag formats
THINKING_PATTERNS = [
    re.compile(r"<think>(.*?)</think>", re.DOTALL),
    re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL),
    re.compile(r"<reason>(.*?)</reason>", re.DOTALL),
    re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL),
    re.compile(r"<\|begin_of_thought\|>(.*?)<\|end_of_thought\|>", re.DOTALL),
]


def parse_thinking(text: str) -> ThinkingResult:
    """
    Extract thinking blocks from LLM output.
    
    Handles formats from Qwen3 (<think>), DeepSeek-R1 (<reasoning>),
    and other reasoning models.
    
    Returns ThinkingResult with thinking stripped from content.
    """
    if not text:
        return ThinkingResult(thinking=None, content="")
    
    thinking_parts = []
    clean_text = text
    
    for pattern in THINKING_PATTERNS:
        matches = pattern.findall(clean_text)
        if matches:
            thinking_parts.extend(matches)
            clean_text = pattern.sub("", clean_text)
    
    # Clean up whitespace
    clean_text = clean_text.strip()
    thinking = "\n".join(t.strip() for t in thinking_parts).strip() if thinking_parts else None
    
    return ThinkingResult(thinking=thinking, content=clean_text)


def strip_thinking(text: str) -> str:
    """Quick helper — return only the content without thinking blocks."""
    return parse_thinking(text).content
