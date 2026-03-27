"""CVA Multi-Agent Orchestrator — v3 redesign using LangGraph Command routing.

Architecture (simplified for reliability):
  Supervisor node decides which specialist to call next via a routing prompt.
  Each specialist is just a ReAct agent that runs in the same graph context.
  State flows through a shared MessagesState — no nested graph invocations.

Specialist agents share the same LLM and checkpointer but have distinct
system prompts injected at call time via the 'prompt' parameter.
"""

import operator
from typing import Annotated, Any, Literal, Optional, Sequence, TypedDict

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from src.brain.llm_provider import get_llm
from src.agents.registry import list_agents, AgentDef
from src.config import settings

THREAD_ID = "cva-session-1"

# ── Supervisor System Prompt ──────────────────────────────────────────────────

_SUPERVISOR_TEMPLATE = """\
You are the CVA Supervisor — an AI penetration testing coordinator.
Route each user request to exactly ONE specialist agent.

Available specialists:
{agents}

Rules:
- Reply with ONLY the agent name (lowercase, no punctuation): recon, exploit, post_exploit, or reporter
- recon     → network scanning, OSINT, technology fingerprinting, directory enumeration
- exploit   → SQL injection, XSS, password attacks, known CVEs, Metasploit
- post_exploit → privilege escalation, lateral movement, credential harvesting, persistence
- reporter  → summarizing findings, writing reports, executive summaries

Say only the agent name. Nothing else.
"""


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    active_agent: str  # tracks which specialist ran last


# ── Orchestrator ──────────────────────────────────────────────────────────────

class Orchestrator:
    """CVA orchestrator with supervisor routing between specialist agents."""

    def __init__(self, tools: list, mode: str = "supervisor"):
        self.mode = mode
        self.all_tools = tools
        self.llm = get_llm()
        self.checkpointer = MemorySaver()
        self._last_agent = "recon"
        self._agent_defs: list[AgentDef] = list_agents()
        self.target: str = ""          # Set via /target or --target; injected into prompts
        self.graph = self._build()

    # ── Graph construction ────────────────────────────────────────────────────

    def _build(self):
        if self.mode == "single":
            return self._build_single()
        return self._build_supervisor()

    def _build_single(self):
        """Legacy: single ReAct agent with all tools and a full pentesting prompt."""
        return create_react_agent(
            self.llm,
            tools=self.all_tools,
            checkpointer=self.checkpointer,
            prompt=self._unified_prompt(),
        )

    def _build_supervisor(self):
        """Supervisor + specialist nodes in one flat StateGraph."""
        agent_list_str = "\n".join(
            f"- {a.name}: {a.description}" for a in self._agent_defs
        )
        supervisor_prompt = _SUPERVISOR_TEMPLATE.format(agents=agent_list_str)

        graph = StateGraph(AgentState)

        # ── Supervisor node ───────────────────────────────────────────────────
        def supervisor(state: AgentState) -> dict:
            """Route to the appropriate specialist."""
            msgs = state["messages"]
            # Give supervisor last 6 messages for context
            context = msgs[-6:] if len(msgs) > 6 else msgs
            routing_msgs = [SystemMessage(content=supervisor_prompt)] + list(context)

            resp = self.llm.invoke(routing_msgs)
            from src.brain.thinking import strip_thinking
            raw = strip_thinking(resp.content).strip().lower()

            valid = {a.name for a in self._agent_defs}
            chosen = self._last_agent
            for name in valid:
                if name in raw:
                    chosen = name
                    break

            self._last_agent = chosen
            return {"active_agent": chosen, "messages": []}

        graph.add_node("supervisor", supervisor)

        # ── Specialist nodes ──────────────────────────────────────────────────
        for agent_def in self._agent_defs:
            filtered = agent_def.filter_tools(self.all_tools) or self.all_tools
            specialist_llm = self.llm.bind_tools(filtered)
            sys_prompt = agent_def.system_prompt

            def make_specialist(llm_with_tools, prompt, tools_list, orchestrator_ref):
                def specialist(state: AgentState) -> dict:
                    """Run one ReAct round for this specialist."""
                    msgs = list(state["messages"])
                    # Build system prompt — include target if set
                    full_prompt = prompt
                    if orchestrator_ref.target:
                        full_prompt = (
                            f"TARGET: {orchestrator_ref.target}\n"
                            f"You are performing an AUTHORIZED penetration test against this target.\n\n"
                            + prompt
                        )
                    system = SystemMessage(content=full_prompt)
                    result = llm_with_tools.invoke([system] + msgs)
                    new_msgs = [result]

                    # If the LLM called tools, execute them
                    if hasattr(result, "tool_calls") and result.tool_calls:
                        tool_map = {t.name: t for t in tools_list}
                        for tc in result.tool_calls:
                            tool = tool_map.get(tc["name"])
                            if tool:
                                try:
                                    tool_output = tool.invoke(tc["args"])
                                except Exception as e:
                                    tool_output = f"Tool error: {e}"
                            else:
                                tool_output = f"Unknown tool: {tc['name']}"
                            new_msgs.append(ToolMessage(
                                content=str(tool_output),
                                tool_call_id=tc["id"],
                                name=tc["name"],
                            ))

                        # Let the specialist synthesize results
                        synthesis = llm_with_tools.invoke([system] + msgs + new_msgs)
                        new_msgs.append(synthesis)

                    return {"messages": new_msgs}
                return specialist

            node_name = agent_def.name
            graph.add_node(
                node_name,
                make_specialist(specialist_llm, sys_prompt, filtered, self)
            )

        # ── Routing ───────────────────────────────────────────────────────────
        def route(state: AgentState) -> str:
            return state.get("active_agent", "recon")

        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            route,
            {a.name: a.name for a in self._agent_defs},
        )
        for agent_def in self._agent_defs:
            graph.add_edge(agent_def.name, END)

        return graph.compile(checkpointer=self.checkpointer)

    # ── Public API ────────────────────────────────────────────────────────────

    def invoke(self, user_input: str, thread_id: str = None) -> dict:
        """Run the agent graph and return state dict."""
        tid = thread_id or THREAD_ID
        config = {"configurable": {"thread_id": tid}}
        return self.graph.invoke(
            {"messages": [HumanMessage(content=user_input)], "active_agent": self._last_agent},
            config=config,
        )

    def stream(self, user_input: str, thread_id: str = None):
        """Stream agent execution at message fragment level.
        Yields (chunk, metadata) tuples where chunk is a message fragment.
        """
        tid = thread_id or THREAD_ID
        config = {"configurable": {"thread_id": tid}}
        return self.graph.stream(
            {"messages": [HumanMessage(content=user_input)], "active_agent": self._last_agent},
            config=config,
            stream_mode="messages",
        )

    def stream_updates(self, user_input: str, thread_id: str = None):
        """Stream agent execution at state-update level.
        Yields dicts like {'node_name': {'messages': [...], 'active_agent': '...'}}
        Each dict corresponds to one node completing its work.
        This gives us the full batch of messages (including tool calls + results)
        from each node as soon as the node finishes.
        """
        tid = thread_id or THREAD_ID
        config = {"configurable": {"thread_id": tid}}
        return self.graph.stream(
            {"messages": [HumanMessage(content=user_input)], "active_agent": self._last_agent},
            config=config,
            stream_mode="updates",
        )

    def get_messages(self, thread_id: str = None) -> list:
        tid = thread_id or THREAD_ID
        config = {"configurable": {"thread_id": tid}}
        try:
            state = self.graph.get_state(config)
            return list(state.values.get("messages", []))
        except Exception:
            return []

    def update_messages(self, messages: list, thread_id: str = None):
        tid = thread_id or THREAD_ID
        config = {"configurable": {"thread_id": tid}}
        try:
            self.graph.update_state(config, {"messages": messages})
        except Exception:
            pass

    def inject_message(self, message: BaseMessage, thread_id: str = None):
        """Inject a message (e.g. /run output) into conversation history."""
        tid = thread_id or THREAD_ID
        config = {"configurable": {"thread_id": tid}}
        try:
            self.graph.update_state(config, {"messages": [message]})
        except Exception:
            pass

    def set_target(self, target: str):
        """Set the pentest target. It will be injected into all agent prompts."""
        self.target = target.strip().rstrip("/")
        # Inject a system-level context message so the LLM knows immediately
        self.inject_message(
            SystemMessage(
                content=(
                    f"[TARGET UPDATED] The penetration test target is now: {self.target}\n"
                    f"All subsequent actions should be directed at this target."
                )
            )
        )

    def switch_model(self, provider: str, model: str = None):
        """Hot-swap the LLM and rebuild the graph."""
        if model:
            attr = f"{provider}_model"
            if hasattr(settings, attr):
                setattr(settings, attr, model)
        settings.llm_provider = provider
        self.llm = get_llm(provider, model)
        self.graph = self._build()

    @property
    def active_agent(self) -> str:
        return self._last_agent

    # ── Private ───────────────────────────────────────────────────────────────

    def _unified_prompt(self) -> str:
        target_line = (
            f"\nTARGET: {self.target}\nAll testing must be directed at this target.\n"
            if self.target else ""
        )
        return f"""\
You are CVA (Cognitive VAPT Assistant) — an AI penetration testing operator.
{target_line}
You EXECUTE tools directly. You do NOT advise the user to run them.

Follow the standard VAPT methodology:
1. Reconnaissance — scan networks, gather OSINT, fingerprint services
2. Enumeration   — enumerate web dirs, services, technologies
3. Vulnerability — identify weaknesses via automated + manual testing
4. Exploitation  — validate vulns with controlled exploitation
5. Post-Exploit  — escalate privileges, harvest credentials, move laterally
6. Reporting     — document findings with evidence and remediation

Rules:
- Run tools immediately when needed, do not ask permission
- Use shell sessions for interactive tools (netcat, Metasploit)
- Document exact commands and outputs as evidence
- Only test what is in scope
"""
