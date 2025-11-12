"""Built-in agents module"""

from .general import AGENT_CONFIG as GENERAL_AGENT
from .coding import AGENT_CONFIG as CODING_AGENT
from .conversational import AGENT_CONFIG as CONVERSATIONAL_AGENT

__all__ = [
    "GENERAL_AGENT",
    "CODING_AGENT",
    "CONVERSATIONAL_AGENT",
]
