"""CVA Agent System — specialist agents with handoff routing.

Inspired by CAI's multi-agent architecture but built on LangGraph.
Each specialist agent has a focused system prompt and curated tool set.
A supervisor agent routes to the right specialist based on context.
"""

from src.agents.registry import AGENT_REGISTRY, get_agent, list_agents
