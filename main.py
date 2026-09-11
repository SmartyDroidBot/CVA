"""CVA — Cognitive VAPT Assistant v3

Multi-agent penetration testing assistant with:
- Supervisor routing to specialist agents (recon, exploit, post-exploit, reporter)
- Interactive PTY shell sessions
- Prompt injection guardrails
- RAG knowledge enrichment (static + vector)
- Session persistence (MongoDB or in-memory)
- Human-in-the-loop tool approval
"""

import atexit
import sys
from typing import Optional, List

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src.config import settings
from src.ui import cli
from src.ui.commands import CommandHandler
from src.orchestrator import Orchestrator, THREAD_ID
from src.tracker.task_tree import TaskTree
from src.reporting.generator import ReportGenerator, Finding
from src.memory.summarizer import Summarizer
from src.memory.session_logger import SessionLogger
from src.knowledge.rag import DoubleRAG


# ── Tool Loading ─────────────────────────────────────────────────────────────

def _load_tools() -> List[StructuredTool]:
    """Load MCP tools + shell session tools. Returns combined list."""
    all_tools = []

    # MCP tools from config/mcp_servers.yaml
    try:
        from src.tools.mcp_client import get_mcp_tools
        mcp_tools = get_mcp_tools()
        all_tools.extend(mcp_tools)
        cli.print_status(f"Loaded {len(mcp_tools)} MCP tools.")
    except Exception as e:
        cli.print_error(f"MCP tool loading failed: {e}")

    # Interactive shell session tools
    try:
        from src.tools.shell_session import get_session_tools
        session_tools = get_session_tools()
        all_tools.extend(session_tools)
        cli.print_status(f"Loaded {len(session_tools)} shell session tools.")
    except Exception as e:
        cli.print_error(f"Shell session tools failed: {e}")

    return all_tools


# ── Approval Gate ────────────────────────────────────────────────────────────

# Read-only tools that never modify the target — no approval prompt needed.
READ_ONLY_TOOLS = {
    "search_knowledge_base", "read_local_file",
    "search_exploits", "examine_exploit",
}


def _apply_approval_gate(tools: List[StructuredTool]) -> List[StructuredTool]:
    """Wrap tools with human-in-the-loop approval (read-only tools pass through)."""
    from src.guardrails.command import check_command

    gated = []
    for tool in tools:
        original_func = tool.func

        def _gated_func(_fn=original_func, _name=tool.name, **kwargs):
            if not settings.require_approval or _name in READ_ONLY_TOOLS:
                return _fn(**kwargs)

            # Command guardrail check (output-side)
            if settings.guardrails_enabled and "command" in kwargs:
                cmd_check = check_command(str(kwargs["command"]))
                if not cmd_check.is_safe:
                    cli.print_error(f"🛡️ BLOCKED by guardrail: {cmd_check.summary}")
                    return f"Command blocked by safety guardrail: {cmd_check.summary}"
                elif cmd_check.triggers:
                    cli.print_status(f"⚠️ Guardrail warning: {cmd_check.summary}", style="bold yellow")

            response = cli.get_tool_approval(_name, kwargs)

            if response == "approve":
                return _fn(**kwargs)
            elif response == "skip":
                return f"[Tool {_name} was denied by the user. Adjust your approach or ask the user for guidance.]"
            else:
                return f"[User feedback instead of running {_name}: {response}]"

        gated_tool = StructuredTool.from_function(
            func=_gated_func,
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            return_direct=getattr(tool, "return_direct", False),
        )
        gated.append(gated_tool)

    return gated


# ── Session Store (graceful fallback) ────────────────────────────────────────

def _init_session_store():
    """Try MongoDB, fall back to None."""
    try:
        from src.memory.session_store import SessionStore
        store = SessionStore()
        # Test connection
        store.list_sessions()
        cli.print_status("MongoDB session store connected.")
        return store
    except Exception:
        cli.print_status("MongoDB unavailable — sessions will not persist.", style="yellow")
        return None


# ── RAG Knowledge System ─────────────────────────────────────────────────────

def _init_rag():
    """Initialize the DoubleRAG knowledge system."""
    vector_kb = None
    try:
        from src.knowledge.vector_kb import VectorKB
        vkb = VectorKB()
        if vkb.available:
            vector_kb = vkb
            cli.print_status("Vector KB connected (Qdrant).")
        else:
            cli.print_status("Vector KB unavailable — using static KB only.", style="yellow")
    except Exception:
        cli.print_status("Vector KB init failed — using static KB only.", style="yellow")

    rag = DoubleRAG(vector_kb=vector_kb)
    cli.print_status("Static knowledge base loaded (always on).")
    return rag, vector_kb


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    cli.print_banner()

    # 1. Knowledge system (built first so the KB tool can be wired into the agent)
    rag, vector_kb = _init_rag()

    # 2. Load tools
    cli.print_status("Loading tools...")
    tools = _load_tools()
    if not tools:
        cli.print_error("No tools loaded. Check config/mcp_servers.yaml")
        sys.exit(1)

    # 2b. Register the knowledge-base search tool so the agent can query the KB.
    try:
        from src.tools.kb_tool import setup_kb_tool, search_knowledge_base
        setup_kb_tool(rag)
        tools.append(search_knowledge_base)
        cli.print_status("Knowledge-base tool registered (search_knowledge_base).")
    except Exception as e:
        cli.print_error(f"KB tool registration failed: {e}")

    # 3. Apply approval gate
    if settings.require_approval:
        tools = _apply_approval_gate(tools)
        cli.print_status("Approval gate active (use /approval off to disable).")

    # 4. Initialize orchestrator
    cli.print_status(f"Initializing agent (mode: {settings.agent_mode})...")
    orchestrator = Orchestrator(tools=tools, mode=settings.agent_mode)

    # 5. Session store
    session_store = _init_session_store()

    # 6. Other subsystems
    task_tree = TaskTree()
    report_gen = ReportGenerator()
    session_logger = SessionLogger()
    summarizer = Summarizer(llm=orchestrator.llm)

    # 7. Command handler
    cmd_handler = CommandHandler(
        orchestrator=orchestrator,
        tools=tools,
        session_store=session_store,
        task_tree=task_tree,
        report_gen=report_gen,
        session_logger=session_logger,
        vector_kb=vector_kb,
    )

    # 8. Auto-create session if configured
    if settings.auto_session:
        if session_store:
            sid = session_store.create_session("auto")
            cmd_handler.current_session_id = sid
            session_logger.switch_session(sid)
            cli.print_status(f"Auto-session created: {sid}")
        else:
            session_logger.switch_session("local")
            cli.print_status("Local session logging active.")

    # 9. Register cleanup
    def _cleanup():
        from src.tools.shell_session import shutdown_all as shutdown_sessions
        shutdown_sessions()
        try:
            from src.tools.mcp_client import shutdown_mcp
            shutdown_mcp()
        except Exception:
            pass
        if session_store:
            session_store.close()

    atexit.register(_cleanup)

    cli.print_success("CVA v3 ready. Type a message or /help for commands.")
    cli.print_separator()

    # ── Main Loop ────────────────────────────────────────────────────────────

    while True:
        try:
            user_input = cli.get_user_input()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input.strip():
            continue

        # Handle slash commands
        if cmd_handler.is_command(user_input):
            session_logger.log_user_input(user_input)
            output, action = cmd_handler.execute(user_input)

            if output:
                cli.print_command_output(output)
                session_logger.log_command(user_input, output)

            if action == "exit":
                break
            elif action == "clear":
                cli.console.clear()
            elif action and action.startswith("inject:"):
                # /run output injection into agent context
                inject_text = action[7:]
                orchestrator.inject_message(
                    HumanMessage(content=inject_text), THREAD_ID
                )
                cli.print_status("Command output injected into agent context.")
            continue

        # ── Input Guardrails ─────────────────────────────────────────────────
        if settings.guardrails_enabled:
            from src.guardrails.injection import check_input
            check = check_input(user_input, threshold=settings.guardrail_threshold)
            if not check.is_safe:
                cli.print_error(f"🛡️ Input blocked by guardrail: {check.summary}")
                session_logger.log_event("guardrail", f"Input blocked: {check.summary}")
                continue
            # Use sanitized input if unicode was normalized
            if check.sanitized:
                user_input = check.sanitized

        # Log user input
        session_logger.log_user_input(user_input)

        # ── RAG context enrichment ───────────────────────────────────────────
        phase = task_tree.current_phase.value if task_tree else "reconnaissance"
        rag_ctx = rag.get_context(phase, user_input)

        # Build enhanced input — target is injected once at session level via
        # orchestrator.set_target(), not repeated in every message.
        if rag_ctx:
            enhanced_input = f"{user_input}\n\n[KNOWLEDGE CONTEXT]\n{rag_ctx}"
        else:
            enhanced_input = user_input

        # ── Agent invocation ─────────────────────────────────────────────────
        try:
            if settings.show_thinking:
                # Streaming mode for thinking display
                stream = orchestrator.stream(enhanced_input, THREAD_ID)
                result = cli.stream_agent_response(stream)

                response_content = result.get("content", "")
                tool_results = result.get("tool_results", [])

                if not response_content and not tool_results:
                    cli.print_status("Agent produced no response.", style="yellow")
                elif response_content:
                    cli.print_agent_response(response_content)

                # Show tool results
                for tr in tool_results:
                    cli.print_tool_result(tr["name"], tr["content"])
                    session_logger.log_tool_result(tr["name"], tr["content"])

                    # Track in task tree
                    if task_tree:
                        task_tree.add_action(
                            action=f"Tool: {tr['name']}",
                            tool=tr["name"],
                            result_summary=tr["content"][:100],
                        )
            else:
                # Non-streaming mode
                result = orchestrator.invoke(enhanced_input, THREAD_ID)
                messages = result.get("messages", [])

                tool_cmds = {}  # tool_call_id -> command string (for phase inference)
                for msg in messages:
                    if isinstance(msg, AIMessage):
                        for tc in (getattr(msg, "tool_calls", None) or []):
                            args = tc.get("args", {}) or {}
                            tool_cmds[tc.get("id")] = (
                                args.get("command", "") if isinstance(args, dict) else ""
                            )
                        if msg.content:
                            content = msg.content if isinstance(msg.content, str) else str(msg.content)
                            cli.print_agent_response(content)
                            session_logger.log_agent_response(content)

                    elif isinstance(msg, ToolMessage):
                        cli.print_tool_result(msg.name, msg.content)
                        session_logger.log_tool_result(msg.name, msg.content)

                        if task_tree:
                            task_tree.add_action(
                                action=f"Tool: {msg.name}",
                                tool=msg.name,
                                result_summary=msg.content[:100],
                                command=tool_cmds.get(getattr(msg, "tool_call_id", None), ""),
                            )

        except KeyboardInterrupt:
            cli.print_status("\nAgent interrupted by user.", style="yellow")
            continue
        except Exception as e:
            cli.print_error(f"Agent error: {e}")
            session_logger.log_event("error", str(e))
            if settings.debug_mode:
                import traceback
                traceback.print_exc()
            continue

        # ── Summarization check ──────────────────────────────────────────────
        messages = orchestrator.get_messages(THREAD_ID)
        if summarizer.should_summarize(messages):
            try:
                summary_text, new_messages = summarizer.summarize(messages)
                if summary_text:
                    orchestrator.update_messages(new_messages, THREAD_ID)
                    cli.print_status(f"Context summarized ({len(messages)} → {len(new_messages)} messages).")
                    session_logger.log_event("summary", summary_text[:200])

                    # Save summary to session store
                    if session_store and cmd_handler.current_session_id:
                        session_store.update_summary(cmd_handler.current_session_id, summary_text)
            except Exception as e:
                cli.print_status(f"Summarization skipped: {e}", style="yellow")

        # ── Auto-save to session store ───────────────────────────────────────
        if session_store and cmd_handler.current_session_id:
            try:
                messages = orchestrator.get_messages(THREAD_ID)
                session_store.save_messages(cmd_handler.current_session_id, messages)
            except Exception:
                pass

    # ── Shutdown ─────────────────────────────────────────────────────────────
    cli.print_status("Shutting down CVA...")
    _cleanup()


if __name__ == "__main__":
    main()
