"""General purpose AI assistant agent"""

from ..base import AgentConfig

AGENT_CONFIG = AgentConfig(
    name="general",
    description="General purpose AI assistant for everyday tasks",
    system_prompt="""You are a helpful, friendly, and knowledgeable AI assistant. 
You provide clear, accurate, and concise answers to user questions.
You are respectful, professional, and aim to be as helpful as possible.""",
    temperature=0.7,
)
