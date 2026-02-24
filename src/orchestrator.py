"""LangGraph ReAct Orchestrator with Human-in-the-Loop."""

from typing import List
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from src.brain.llm_provider import get_llm
from src.config import settings


SYSTEM_PROMPT = """You are CVA (Cognitive VAPT Assistant), an expert AI penetration testing assistant.

## Your Role
You guide users through the VAPT (Vulnerability Assessment & Penetration Testing) lifecycle. You think strategically, explain your reasoning, and suggest the most appropriate next action.

## Behavior Rules
1. **Always explain your reasoning** before suggesting a tool call. State your hypothesis, what you expect to find, and why this step matters.
2. **Follow VAPT methodology**: Reconnaissance → Enumeration → Vulnerability Analysis → Exploitation → Post-Exploitation → Reporting.
3. **Be specific**: Suggest exact tool calls with specific parameters, not vague guidance.
4. **Summarize results**: After each tool execution, summarize findings and suggest the next step.
5. **Track findings**: Keep track of discovered hosts, ports, services, and vulnerabilities.
6. **If the user is just chatting or brainstorming**, respond conversationally WITHOUT suggesting tool calls.
7. **Safety first**: Always remind the user to only test systems they have authorization to test.

## Available Tool Categories
- **Reconnaissance**: nmap_scan, gobuster_dir, nikto_scan
- **Research**: search_exploitdb, search_web
- **Execution**: execute_shell_command (last resort), execute_sandboxed_script (for custom scripts)

## Output Style
- Be concise but thorough
- Use bullet points for findings
- Highlight critical discoveries (open ports, vulnerabilities, credentials)
"""


class Orchestrator:
    """ReAct agent with human-in-the-loop approval for tool calls."""
    
    def __init__(self, tools: List[BaseTool], provider: str = None, model: str = None):
        self.tools = tools
        self.checkpointer = MemorySaver()
        self._build_agent(provider, model)
    
    def _build_agent(self, provider: str = None, model: str = None):
        """Build or rebuild the LangGraph ReAct agent."""
        self.llm = get_llm(provider, model)
        self.agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=SYSTEM_PROMPT,
            checkpointer=self.checkpointer,
        )
    
    def switch_model(self, provider: str, model: str = None):
        """Switch to a different LLM provider/model at runtime."""
        self._build_agent(provider, model)
    
    def get_config(self, thread_id: str = "default") -> dict:
        """Get LangGraph config for a specific conversation thread."""
        return {"configurable": {"thread_id": thread_id}}
    
    def invoke(self, user_input: str, thread_id: str = "default") -> dict:
        """
        Send user input to the agent and get a response.
        
        Returns the full agent state including messages.
        """
        config = self.get_config(thread_id)
        result = self.agent.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
        )
        return result
    
    def stream(self, user_input: str, thread_id: str = "default"):
        """
        Stream agent execution, yielding events as they occur.
        
        Yields dicts with 'type' and 'content' keys.
        """
        config = self.get_config(thread_id)
        
        for event in self.agent.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
            stream_mode="updates",
        ):
            yield event
    
    def get_state(self, thread_id: str = "default"):
        """Get current agent state for a thread."""
        config = self.get_config(thread_id)
        return self.agent.get_state(config)
    
    def get_messages(self, thread_id: str = "default") -> list:
        """Get all messages for a thread."""
        state = self.get_state(thread_id)
        return state.values.get("messages", [])
