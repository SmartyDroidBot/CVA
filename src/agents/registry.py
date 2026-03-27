"""Agent Registry — maps agent names to their definitions.

Each agent is a dict with: name, system_prompt, tool_filter, description.
The orchestrator converts these into LangGraph sub-agents at runtime.
"""

from typing import Dict, List, Optional, Callable

# ── Agent definition type ────────────────────────────────────────────────────

class AgentDef:
    """Lightweight agent definition used by the orchestrator."""

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tool_filter: Optional[Callable] = None,
        temperature: float = 0,
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.tool_filter = tool_filter  # fn(tool_list) -> filtered tool_list
        self.temperature = temperature

    def filter_tools(self, all_tools: list) -> list:
        """Return only the tools this agent should have access to."""
        if self.tool_filter is None:
            return all_tools
        return self.tool_filter(all_tools)

    def __repr__(self):
        return f"AgentDef(name={self.name!r})"


# ── Global registry ──────────────────────────────────────────────────────────

AGENT_REGISTRY: Dict[str, AgentDef] = {}


def register_agent(agent: AgentDef):
    """Register an agent definition."""
    AGENT_REGISTRY[agent.name.lower()] = agent


def get_agent(name: str) -> Optional[AgentDef]:
    """Get an agent definition by name (case-insensitive)."""
    return AGENT_REGISTRY.get(name.lower())


def list_agents() -> List[AgentDef]:
    """List all registered agent definitions."""
    return list(AGENT_REGISTRY.values())


# ── Auto-register all specialist agents on import ────────────────────────────

def _auto_register():
    """Import all agent modules so they self-register."""
    from src.agents import recon, exploit, post_exploit, reporter  # noqa: F401

_auto_register()
