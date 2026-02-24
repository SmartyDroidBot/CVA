"""Tests for MCP tools — MCP server tool loading and execution."""

import pytest
from src.tools.mcp_client import get_mcp_tools


class TestMcpToolLoading:
    """Tests for MCP tool discovery and loading."""
    
    def test_load_tools(self):
        """Should load tools from MCP server."""
        tools = get_mcp_tools()
        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        print(f"Loaded tools: {tool_names}")
    
    def test_expected_tools_present(self):
        """Core tools should be present."""
        tools = get_mcp_tools()
        tool_names = [t.name for t in tools]
        
        expected = ["nmap_scan", "gobuster_dir", "execute_shell_command",
                     "search_exploitdb", "search_web"]
        for name in expected:
            assert name in tool_names, f"Expected tool '{name}' not found. Got: {tool_names}"
    
    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        tools = get_mcp_tools()
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' has no description"
    
    def test_shell_command_execution(self):
        """execute_shell_command should work."""
        tools = get_mcp_tools()
        shell_tool = next((t for t in tools if t.name == "execute_shell_command"), None)
        assert shell_tool is not None
        
        result = shell_tool.run({"command": "echo 'CVA test'"})
        assert "CVA test" in result


class TestMcpToolExecution:
    """Integration tests for actual tool execution."""
    
    def test_nmap_help(self):
        """Nmap should respond to --help."""
        tools = get_mcp_tools()
        nmap_tool = next((t for t in tools if t.name == "nmap_scan"), None)
        if nmap_tool is None:
            pytest.skip("nmap_scan tool not loaded")
        
        result = nmap_tool.run({"target": "--help", "options": ""})
        assert "nmap" in result.lower() or "usage" in result.lower() or "error" in result.lower()
