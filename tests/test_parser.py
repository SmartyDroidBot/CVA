"""Tests for Intelligent Parser module."""

import pytest
from src.parser.intelligent_parser import IntelligentParser


class TestIntelligentParser:
    """Tests for raw output parsing."""
    
    def test_quick_summary(self):
        """Quick summary should return basic stats."""
        parser = IntelligentParser()
        output = "Port 80 open\nPort 443 open\nPort 22 open"
        summary = parser.quick_summary(output, "nmap")
        assert "nmap" in summary
        assert "3 lines" in summary
    
    def test_empty_output(self):
        """Empty output should return gracefully."""
        parser = IntelligentParser()
        result = parser.parse("", "nmap")
        assert "key_findings" in result
    
    def test_short_output(self):
        """Very short output should be handled."""
        parser = IntelligentParser()
        result = parser.parse("ok", "test")
        assert "key_findings" in result
