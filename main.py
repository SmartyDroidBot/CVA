#!/usr/bin/env python3
"""CVA — Cognitive VAPT Assistant. Entry point."""

import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import settings
from src.orchestrator import Orchestrator
from src.tools.mcp_client import get_mcp_tools
from src.ui import cli
from src.ui.commands import CommandHandler
from src.brain.thinking import parse_thinking
from src.memory.session_store import SessionStore
from src.memory.summarizer import Summarizer
from src.parser.intelligent_parser import IntelligentParser
from src.reporting.generator import ReportGenerator, Finding
from src.tracker.task_tree import TaskTree, TOOL_PHASE_MAP
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


def main():
    """Main CVA loop."""
    cli.print_banner()
    
    # ── Load Tools ──
    cli.print_status("Loading MCP tools...")
    try:
        tools = get_mcp_tools()
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
    
    # ── Command Handler ──
    cmd_handler = CommandHandler(
        orchestrator=orchestrator, tools=tools,
        session_store=session_store, task_tree=task_tree,
        report_gen=report_gen,
    )
    
    cli.print_separator()
    thread_id = "session_default"
    
    # ── Main Loop ──
    while True:
        try:
            user_input = cli.get_user_input()
            
            if not user_input.strip():
                continue
            
            # ── Handle Slash Commands ──
            if cmd_handler.is_command(user_input):
                output, action = cmd_handler.execute(user_input)
                
                if action == "exit":
                    # Auto-save session before exit
                    if session_store and cmd_handler.current_session_id:
                        messages = orchestrator.get_messages(thread_id)
                        session_store.save_messages(cmd_handler.current_session_id, messages)
                        cli.print_info(f"Session {cmd_handler.current_session_id} auto-saved.")
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
                        except Exception:
                            pass  # Don't fail on parse errors
                    continue
                else:
                    cli.print_command_output(output)
                    continue
            
            # ── Send to Agent ──
            cli.print_status("Thinking...")
            
            try:
                # Inject progress context if active
                enhanced_input = user_input
                progress_ctx = task_tree.get_context_for_agent()
                if progress_ctx:
                    enhanced_input = f"{progress_ctx}\n\nUser: {user_input}"
                
                result = orchestrator.invoke(enhanced_input, thread_id=thread_id)
                messages = result.get("messages", [])
                
                # Extract response components
                last_content, tool_calls, tool_results = extract_last_response(messages)
                
                # Track tool calls in task tree
                for tr in tool_results:
                    task_tree.add_action(
                        action=tr["name"],
                        tool=tr["name"],
                        result_summary=tr["content"][:80] if tr["content"] else "",
                    )
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
                
                # Auto-summarize if needed
                if summarizer.should_summarize(messages):
                    cli.print_status("Compressing context...")
                    summary_text, new_msgs = summarizer.summarize(messages)
                    if summary_text and session_store and cmd_handler.current_session_id:
                        session_store.update_summary(
                            cmd_handler.current_session_id, summary_text
                        )
                        cli.print_info("Context summarized and saved.")
                
            except Exception as e:
                cli.print_error(f"Agent error: {e}")
                if settings.debug_mode:
                    import traceback
                    cli.print_error(traceback.format_exc())
            
            cli.print_separator()
            
        except KeyboardInterrupt:
            cli.print_info("\nUse /exit to quit.")
            continue
    
    # Cleanup
    if session_store:
        session_store.close()


if __name__ == "__main__":
    main()
