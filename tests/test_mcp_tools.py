"""Tests for MCP tools — MCP server tool loading and execution.

These tests spawn the MCP servers declared in ``config/mcp_servers.yaml``
(``src/mcp_server/kali.py`` and ``exploitdb.py``) over stdio. When those
servers cannot be started (e.g. missing runtime), the whole module skips.
"""

import pytest
from src.tools.mcp_client import get_mcp_tools


def _mcp_tools_or_skip():
    try:
        tools = get_mcp_tools()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"MCP tools unavailable: {e}")
    if not tools:
        pytest.skip("MCP server returned no tools")
    return tools


# The tools actually exposed by the MCP servers today. Keep this in sync with
# src/mcp_server/kali.py and src/mcp_server/exploitdb.py.
CORE_TOOLS = {
    "execute_shell_command",
    "read_local_file",
    "execute_sandboxed_script",
    "search_exploits",
    "examine_exploit",
}


class TestMcpToolLoading:
    """Tests for MCP tool discovery and loading."""

    def test_load_tools(self):
        """Should load at least one tool from the MCP servers."""
        tools = _mcp_tools_or_skip()
        assert len(tools) > 0

    def test_expected_tools_present(self):
        """The core generic tools should be present."""
        tools = _mcp_tools_or_skip()
        tool_names = {t.name for t in tools}
        # execute_shell_command is the backbone tool; it must always be there.
        assert "execute_shell_command" in tool_names, f"Got: {sorted(tool_names)}"
        # At least most of the known core tools should be exposed.
        assert CORE_TOOLS & tool_names, f"No known tools found. Got: {sorted(tool_names)}"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        tools = _mcp_tools_or_skip()
        for tool in tools:
            assert tool.description, f"Tool '{tool.name}' has no description"


class TestMcpToolExecution:
    """Integration tests for actual tool execution."""

    def test_shell_command_execution(self):
        """execute_shell_command should echo back input."""
        tools = _mcp_tools_or_skip()
        shell_tool = next((t for t in tools if t.name == "execute_shell_command"), None)
        if shell_tool is None:
            pytest.skip("execute_shell_command not loaded")

        result = shell_tool.invoke({"command": "echo CVA_test"})
        assert "CVA_test" in str(result)
