"""LangGraph Agent State definition."""

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """State that flows through the LangGraph ReAct agent."""
    messages: Annotated[list, add_messages]
