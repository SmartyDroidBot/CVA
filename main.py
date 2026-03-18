#!/usr/bin/env python3
"""CVA — Cognitive VAPT Assistant. Entry point."""

import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings
from src.orchestrator import Orchestrator, THREAD_ID
from src.tools.mcp_client import get_mcp_tools, shutdown_mcp
from src.ui import cli
from src.ui.commands import CommandHandler
from src.brain.thinking import parse_thinking
from src.memory.session_store import SessionStore
from src.memory.summarizer import Summarizer
from src.memory.session_logger import SessionLogger
from src.parser.intelligent_parser import IntelligentParser
from src.reporting.generator import ReportGenerator, Finding
from src.tracker.task_tree import TaskTree, TOOL_PHASE_MAP
from src.knowledge.vector_kb import VectorKB
from src.knowledge.rag import DoubleRAG
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage


def extract_last_response(messages: list) -> tuple:
    """Extract the last AI response, tool calls, and tool results from messages."""
    last_ai_content = ""
    tool_calls = []
    tool_results = []
    
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not last_ai_content:
            last_ai_content = msg.content if isinstance(msg.content, str) else str(msg.content)
        elif isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls = msg.tool_calls
        elif isinstance(msg, ToolMessage):
            tool_results.append({"name": msg.name, "content": msg.content})
        elif isinstance(msg, HumanMessage):
            break
    
    return last_ai_content, tool_calls, tool_results


def _apply_approval_gate(tools: list) -> list:
    """Wrap every tool so the user must approve before it executes.

    The gate re-checks settings.require_approval at call-time, so
    /approval on|off takes effect immediately without a restart.
    """
    from langchain_core.tools import StructuredTool

    gated = []
    for tool in tools:
        original_func = tool.func

        def _gated_func(*args, _name=tool.name, _fn=original_func, **kwargs):
            if settings.require_approval:
                decision = cli.get_tool_approval(_name, kwargs)
                if decision == "approve":
                    return _fn(*args, **kwargs)
                elif decision == "skip":
                    return (
                        f"[Tool '{_name}' was denied by the user. "
                        "Do not retry this call. Ask the user how to proceed.]"
                    )
                else:
                    # Custom feedback — return as the tool 'result' so the agent sees it
                    return (
                        f"[User overrode '{_name}' with feedback]: {decision}"
                    )
            # Approval gate off — run directly
            return _fn(*args, **kwargs)

        gated.append(StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            func=_gated_func,
            return_direct=getattr(tool, "return_direct", False),
        ))
    return gated


def main():
    """Main CVA loop."""
    cli.print_banner()
    
    # ── Knowledge Layer ──
    try:
        vector_kb = VectorKB()
        if vector_kb.available:
            stats = vector_kb.get_stats()
            cli.print_info(f"Vector KB ready: {stats.get('points', 0)} chunks in Qdrant.")
        else:
            cli.print_info("Vector KB not available (Qdrant or collection missing). Run: python scripts/ingest_kb.py")
    except Exception as e:
        vector_kb = None
        cli.print_info(f"Vector KB unavailable: {e}")

    # ── Load Tools ──
    cli.print_status("Loading MCP tools...")
    try:
        tools = get_mcp_tools()
        
        # Add Search KB tool natively
        if vector_kb and vector_kb.available:
            from src.tools.kb_tool import search_knowledge_base, setup_kb_tool
            setup_kb_tool(vector_kb)
            tools.append(search_knowledge_base)
            
        tools = _apply_approval_gate(tools)
        cli.print_info(f"Loaded {len(tools)} tools: {', '.join(t.name for t in tools)}")
    except Exception as e:
        cli.print_error(f"Failed to load MCP tools: {e}")
        cli.print_info("Starting without tools. Use /run for manual commands.")
        tools = []
    
    # ── Initialize Agent ──
    cli.print_status(f"Initializing agent ({settings.llm_provider}:{settings.ollama_model})...")
    try:
        orchestrator = Orchestrator(tools=tools)
        cli.print_info("Agent ready.")
    except Exception as e:
        cli.print_error(f"Failed to initialize agent: {e}")
        return
    
    # ── Initialize Sub-Systems ──
    session_store = None
    try:
        session_store = SessionStore()
        cli.print_info("MongoDB session store connected.")
    except Exception as e:
        cli.print_info(f"MongoDB not available: {e} (sessions will be in-memory)")
    
    task_tree = TaskTree()
    report_gen = ReportGenerator()
    summarizer = Summarizer()
    parser = IntelligentParser()
    session_logger = SessionLogger()
    
    # Skip re-initializing KB, just setup RAG
    rag = DoubleRAG(vector_kb=vector_kb, session_store=session_store)
    
    # ── Command Handler ──
    cmd_handler = CommandHandler(
        orchestrator=orchestrator, tools=tools,
        session_store=session_store, task_tree=task_tree,
        report_gen=report_gen, session_logger=session_logger,
        vector_kb=vector_kb,
    )
    
    cli.print_separator()
    
    # ── Main Loop ──
    while True:
        try:
            user_input = cli.get_user_input()
            
            if not user_input.strip():
                continue
            
            # Log user input
            session_logger.log_user_input(user_input)
            
            # ── Handle Slash Commands ──
            if cmd_handler.is_command(user_input):
                output, action = cmd_handler.execute(user_input)
                
                # Log the command
                session_logger.log_command(user_input, output)
                
                if action == "exit":
                    # Auto-save session before exit
                    if session_store and cmd_handler.current_session_id:
                        messages = orchestrator.get_messages(THREAD_ID)
                        session_store.save_messages(cmd_handler.current_session_id, messages)
                        cli.print_info(f"Session {cmd_handler.current_session_id} auto-saved.")
                    session_logger.log_event("exit", "CVA session ended")
                    cli.print_info("Goodbye!")
                    break
                elif action == "clear":
                    os.system("clear" if os.name != "nt" else "cls")
                    cli.print_banner()
                    continue
                elif action == "run_result":
                    cli.print_command_output(output)
                    # Auto-parse raw output into structured data
                    if output and len(output.strip()) > 10:
                        try:
                            cmd_text = user_input.split(maxsplit=1)[1] if " " in user_input else ""
                            parsed = parser.parse(output, tool_name="manual", context=cmd_text)
                            if parsed and not parsed.get("error"):
                                cli.print_info(f"Parsed: {parser.quick_summary(output, 'manual')}")
                                # Save to session if active
                                if session_store and cmd_handler.current_session_id:
                                    for kf in parsed.get("key_findings", []):
                                        session_store.save_note(
                                            cmd_handler.current_session_id,
                                            "manual_scan", kf
                                        )
                                # Track in task tree
                                task_tree.add_action(
                                    action=cmd_text[:50],
                                    tool="execute_shell_command",
                                    result_summary="; ".join(parsed.get("key_findings", []))[:80],
                                )
                                # Log findings
                                for kf in parsed.get("key_findings", []):
                                    session_logger.log_finding(kf, "info", cmd_text)
                        except Exception:
                            pass  # Don't fail on parse errors
                    continue
                else:
                    cli.print_command_output(output)
                    continue
            
            # ── Send to Agent ──
            cli.print_status("Thinking...")
            
            try:
                # Inject knowledge context
                enhanced_input = user_input
                
                # Progress context from task tree
                progress_ctx = task_tree.get_context_for_agent()
                
                # RAG context (static KB + session KB)
                current_phase = task_tree.current_phase.value
                rag_ctx = rag.get_context(
                    phase=current_phase,
                    user_query=user_input,
                    session_id=cmd_handler.current_session_id,
                )
                
                # Build enhanced prompt
                context_parts = []
                if rag_ctx:
                    context_parts.append(rag_ctx)
                if progress_ctx:
                    context_parts.append(progress_ctx)
                
                if context_parts:
                    enhanced_input = "\n\n".join(context_parts) + f"\n\nUser: {user_input}"

                if settings.show_thinking:
                    # ── Streaming path — <think> tokens printed live ───────
                    stream_result = cli.stream_agent_response(
                        orchestrator.stream_tokens(enhanced_input, thread_id=THREAD_ID)
                    )
                    last_content = stream_result["content"]
                    tool_results = stream_result["tool_results"]
                    messages     = orchestrator.get_messages(THREAD_ID)
                    tool_calls   = []
                else:
                    # ── Batch path — existing behaviour ───────────────────
                    result = orchestrator.invoke(enhanced_input, thread_id=THREAD_ID)
                    messages = result.get("messages", [])
                    last_content, tool_calls, tool_results = extract_last_response(messages)

                # Track tool calls in task tree + log
                for tr in tool_results:
                    task_tree.add_action(
                        action=tr["name"],
                        tool=tr["name"],
                        result_summary=tr["content"][:80] if tr["content"] else "",
                    )
                    session_logger.log_tool_result(tr["name"], tr["content"] or "")
                    # Auto-save findings to session
                    if session_store and cmd_handler.current_session_id:
                        session_store.save_note(
                            cmd_handler.current_session_id,
                            f"tool:{tr['name']}",
                            tr["content"][:500] if tr["content"] else "",
                        )

                # Display tool results in debug mode
                for tr in tool_results:
                    cli.print_tool_result(tr["name"], tr["content"])

                # Display agent response
                if last_content:
                    cli.print_agent_response(last_content)
                    session_logger.log_agent_response(last_content)

                # Auto-summarize if needed
                if summarizer.should_summarize(messages):
                    cli.print_status("Compressing context...")
                    summary_text, new_msgs = summarizer.summarize(messages)
                    if summary_text:
                        # Write compressed messages back to the agent's state
                        orchestrator.update_messages(new_msgs, THREAD_ID)
                        session_logger.log_event("summarize", f"Context compressed ({len(messages)} → {len(new_msgs)} messages)")
                        if session_store and cmd_handler.current_session_id:
                            session_store.update_summary(
                                cmd_handler.current_session_id, summary_text
                            )
                            cli.print_info("Context summarized and saved.")

            except Exception as e:
                cli.print_error(f"Agent error: {e}")
                session_logger.log_event("error", str(e))
                if settings.debug_mode:
                    import traceback
                    cli.print_error(traceback.format_exc())
            
            cli.print_separator()
            
        except KeyboardInterrupt:
            # Ctrl+C during agent inference or anywhere outside the prompt
            cli.print_status("")
            cli.print_info("Interrupted.")
            # Auto-save before exit
            if session_store and cmd_handler.current_session_id:
                try:
                    messages = orchestrator.get_messages(THREAD_ID)
                    session_store.save_messages(cmd_handler.current_session_id, messages)
                    cli.print_info(f"Session {cmd_handler.current_session_id} auto-saved.")
                except Exception:
                    pass
            session_logger.log_event("exit", "CVA interrupted (Ctrl+C)")
            cli.print_info("Goodbye!")
            break
    
    # Cleanup
    if session_store:
        session_store.close()
    shutdown_mcp()


if __name__ == "__main__":
    main()
