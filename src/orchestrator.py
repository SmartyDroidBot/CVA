"""LangGraph ReAct Orchestrator with Human-in-the-Loop."""

from typing import List
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from src.brain.llm_provider import get_llm
from src.config import settings

# Centralized thread-id constant — used by main.py, commands.py, etc.
THREAD_ID = "session_default"


SYSTEM_PROMPT = """You are CVA (Cognitive VAPT Assistant), an expert AI penetration testing assistant.

## Your Role
You actively execute the VAPT (Vulnerability Assessment & Penetration Testing) lifecycle on behalf of the user. You think strategically and execute the most appropriate tools to achieve the user's goals.

## Behavior Rules
1. **Be actionable**: Execute exact tool calls with specific parameters immediately. **Do not merely suggest or advise the user to run tools. You must run them yourself using your provided tools.**
2. **Follow VAPT methodology**: Reconnaissance → Enumeration → Vulnerability Analysis → Exploitation → Post-Exploitation → Reporting.
3. **Summarize results**: After each tool execution, summarize findings and autonomously execute the next logical step.
4. **Track findings**: Keep track of discovered hosts, ports, services, and vulnerabilities.
5. **No conversation during scanning**: If you need to run a tool, just run the tool. Do not explain what you are about to do before doing it.
6. **Safety first**: Always remind the user to only test systems they have authorization to test.

## Tool Usage & Shell Execution
- You have a powerful `execute_shell_command` tool. Use your vast knowledge of Kali Linux tools (nmap, gobuster, nikto, sqlmap, hydra, etc.) to construct the exact bash commands you need.
- **Do not guess tool wrappers** — use raw bash commands via `execute_shell_command`. 
- If a command will produce excessive output, pipe it to a file (e.g., `> output.txt`) and read it with `read_local_file`.
- For complex, stateful frameworks (like Metasploit, Burp, BloodHound, ExploitDB), use their dedicated MCP tools if they are available in your toolset.
- **IMPORTANT: You have a `search_knowledge_base` tool. Always query it when you discover new services, encounter unknown errors, or when planning a payload. Do not guess commands if you can look them up.**

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
    
    def get_config(self, thread_id: str = THREAD_ID) -> dict:
        """Get LangGraph config for a specific conversation thread."""
        return {"configurable": {"thread_id": thread_id}}
    
    def invoke(self, user_input: str, thread_id: str = THREAD_ID) -> dict:
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
    
    def stream(self, user_input: str, thread_id: str = THREAD_ID):
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
    
    def get_state(self, thread_id: str = THREAD_ID):
        """Get current agent state for a thread."""
        config = self.get_config(thread_id)
        return self.agent.get_state(config)
    
    def get_messages(self, thread_id: str = THREAD_ID) -> list:
        """Get all messages for a thread."""
        state = self.get_state(thread_id)
        return state.values.get("messages", [])

    def update_messages(self, messages: list, thread_id: str = THREAD_ID):
        """Overwrite the message history in the checkpointer.

        Used by the summarizer (to replace old messages with a summary)
        and by session restore (to inject saved messages).
        """
        config = self.get_config(thread_id)
        self.agent.update_state(config, {"messages": messages})

    def stream_tokens(self, user_input: str, thread_id: str = THREAD_ID):
        """
        Yield (chunk, metadata) at the token level using stream_mode='messages'.

        Suitable for live display of <think> reasoning as it streams.
        Use with cli.stream_agent_response().
        """
        config = self.get_config(thread_id)
        return self.agent.stream(
            {"messages": [HumanMessage(content=user_input)]},
            config=config,
            stream_mode="messages",
        )

