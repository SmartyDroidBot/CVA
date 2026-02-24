"""Intelligent Parser — extracts structured findings from raw command output."""

from langchain_core.messages import HumanMessage, SystemMessage
from src.brain.llm_provider import get_llm
from src.brain.thinking import strip_thinking


PARSER_PROMPT = """You are an intelligent output parser for a penetration testing assistant.

Given raw output from a security tool or command, extract structured findings.

Output a JSON object with these fields (omit empty ones):
{
    "hosts": ["<ip/hostname>", ...],
    "ports": [{"port": 80, "state": "open", "service": "http", "version": "Apache 2.4.49"}],
    "vulnerabilities": [{"name": "...", "severity": "high|medium|low", "details": "..."}],
    "credentials": [{"type": "password|hash|token", "username": "...", "value": "..."}],
    "directories": ["/admin", "/backup", ...],
    "technologies": ["Apache", "PHP 7.4", ...],
    "key_findings": ["Summary of important finding 1", ...],
    "suggested_next": "Brief suggestion for what to investigate next"
}

RULES:
- Be precise — extract EXACT values from the output
- Only include fields that have actual data
- key_findings should be human-readable summaries
- suggested_next should be a brief tactical recommendation
"""


class IntelligentParser:
    """Parses raw command/tool output into structured security findings."""
    
    def __init__(self):
        self.llm = get_llm()
    
    def parse(self, raw_output: str, tool_name: str = "unknown", context: str = "") -> dict:
        """
        Parse raw output into structured findings.
        
        Args:
            raw_output: The raw text output from a tool/command
            tool_name: Name of the tool that produced this output
            context: Additional context (target, current phase, etc.)
        
        Returns:
            Dict with structured findings
        """
        if not raw_output or len(raw_output.strip()) < 10:
            return {"key_findings": ["No significant output to parse."]}
        
        prompt = f"Tool: {tool_name}\n"
        if context:
            prompt += f"Context: {context}\n"
        prompt += f"\nRaw Output:\n```\n{raw_output[:3000]}\n```"
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=PARSER_PROMPT),
                HumanMessage(content=prompt),
            ])
            
            content = strip_thinking(response.content)
            
            # Extract JSON from response
            import json
            import re
            
            # Try to find JSON block in response
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            return {"key_findings": [content[:500]], "raw": True}
            
        except Exception as e:
            return {"key_findings": [f"Parser error: {e}"], "error": True}
    
    def quick_summary(self, raw_output: str, tool_name: str = "") -> str:
        """Quick one-line summary of output (no LLM call — heuristic)."""
        lines = raw_output.strip().splitlines()
        if not lines:
            return "No output."
        
        # Count significant lines (non-empty, non-header)
        sig_lines = [l for l in lines if l.strip() and not l.startswith("#") and not l.startswith("=")]
        
        return f"{tool_name}: {len(sig_lines)} lines of output, {len(raw_output)} chars"
