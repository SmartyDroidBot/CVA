"""Configuration schema definitions using Pydantic models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _default_agents() -> Dict[str, "AgentConfig"]:
    return {
        "general": AgentConfig(
            temperature=0.7,
            system_prompt="You are a helpful AI assistant.",
        ),
        "coding": AgentConfig(
            temperature=0.2,
            preferred_model="codellama",
            system_prompt=(
                "You are an expert programmer. Provide clear, efficient code with explanations."
            ),
        ),
        "conversational": AgentConfig(
            temperature=0.8,
            system_prompt="You are a friendly conversational AI. Be warm, engaging, and personable.",
        ),
    }


def _default_mcp_servers() -> Dict[str, "MCPServerConfig"]:
    import sys

    python_exe = sys.executable
    return {
        "filesystem": MCPServerConfig(
            command=python_exe,
            args=["-m", "cva_cli.mcp_servers.filesystem"],
            enabled=False,
        ),
        "math": MCPServerConfig(
            command=python_exe,
            args=["-m", "cva_cli.mcp_servers.math"],
            enabled=False,
        ),
        "system": MCPServerConfig(
            command=python_exe,
            args=["-m", "cva_cli.mcp_servers.system"],
            enabled=False,
        ),
    }


class BackendConfig(BaseModel):
    """Backend configuration."""

    type: str = "ollama"
    url: str = "http://localhost:11434"
    default_model: str = "qwen3:8b"
    timeout: int = 120


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server."""

    command: str
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    enabled: bool = True
    type: str = "stdio"
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


class AgentConfig(BaseModel):
    """Agent configuration."""

    description: str = "A helpful AI assistant"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    preferred_model: Optional[str] = None


class AppConfig(BaseModel):
    """Top-level application configuration."""

    backend: BackendConfig = Field(default_factory=BackendConfig)
    default_agent: str = "penetration_testing"
    agents: Dict[str, AgentConfig] = Field(default_factory=_default_agents)
    mcp_servers: Dict[str, MCPServerConfig] = Field(default_factory=_default_mcp_servers)
    verbose: bool = False
    color_output: bool = True

    @classmethod
    def default(cls) -> "AppConfig":
        """Return a default configuration instance."""
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-Python dict suitable for serialization."""
        return self.model_dump(mode="python", exclude_none=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Load configuration data from a dict."""
        return cls.model_validate(data)
