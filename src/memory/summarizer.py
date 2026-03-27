"""Summarizer Sub-Agent — compresses conversation context.

FIXED: Now accepts an LLM instance instead of creating its own.
This ensures it tracks /model switches and doesn't spawn duplicate LLMs.
"""

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.language_models import BaseChatModel
from src.brain.llm_provider import get_llm
from src.config import settings


SUMMARIZER_PROMPT = """You are a context summarizer for a cybersecurity penetration testing session.

Given a conversation history, produce a concise summary that PRIORITIZES:
1. **Target information**: IPs, hostnames, URLs, network ranges
2. **Discovered findings**: Open ports, services, versions, technologies
3. **Vulnerabilities found**: CVEs, misconfigurations, injection points
4. **Credentials discovered**: Usernames, passwords, tokens, hashes
5. **Attack surface**: Entry points, interesting directories, API endpoints
6. **Current progress**: What phase of testing we're in, what's been done, what's next

RULES:
- Be concise but lose NO critical data points (ports, IPs, credentials, CVEs)
- Use bullet points
- Group by category
- Drop conversational pleasantries and filler
- Keep tool command history (what was run and key findings)
"""


class Summarizer:
    """Sub-agent that compresses context when messages exceed threshold.

    Accepts an LLM instance to stay in sync with model switches.
    """

    def __init__(self, llm: BaseChatModel = None):
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    @llm.setter
    def llm(self, value: BaseChatModel):
        self._llm = value

    def should_summarize(self, messages: list) -> bool:
        """Check if we should trigger summarization."""
        return len(messages) > settings.max_messages_before_summary

    def summarize(self, messages: list, keep_recent: int = 6) -> tuple:
        """Summarize older messages, keeping the most recent ones.

        Returns:
            (summary_text, new_messages_list) where new_messages_list
            starts with a SystemMessage containing the summary followed
            by the recent messages.
        """
        if len(messages) <= keep_recent:
            return None, messages

        old_messages = messages[:-keep_recent]
        recent_messages = messages[-keep_recent:]

        conversation_text = self._format_messages(old_messages)

        summary_response = self.llm.invoke([
            SystemMessage(content=SUMMARIZER_PROMPT),
            HumanMessage(content=f"Summarize this penetration testing session:\n\n{conversation_text}"),
        ])

        from src.brain.thinking import strip_thinking
        summary_text = strip_thinking(summary_response.content)

        summary_msg = SystemMessage(content=f"[SESSION SUMMARY]\n{summary_text}")
        new_messages = [summary_msg] + recent_messages

        return summary_text, new_messages

    def _format_messages(self, messages: list) -> str:
        """Format LangChain messages into readable text for summarization."""
        lines = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                lines.append(f"USER: {msg.content}")
            elif isinstance(msg, AIMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                lines.append(f"CVA: {content[:500]}")
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        lines.append(f"  → TOOL CALL: {tc['name']}({tc.get('args', {})})")
            elif hasattr(msg, "content"):
                lines.append(f"[{msg.type}]: {msg.content[:300]}")

        return "\n".join(lines)
