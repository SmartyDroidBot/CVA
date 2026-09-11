"""Slash command handler for CVA CLI — v3 with multi-agent, guardrails, sessions.

Changes from v2:
- Removed IntelligentParser dependency
- /run now injects output into agent context
- Added /mode command (supervisor/single)
- Added /agent command (show active agent)
- Added /sessions auto-creation at startup
- Removed sandbox_enabled from /settings
- Added /guardrails toggle
"""

import subprocess
import sys
from typing import Optional, Tuple
from src.config import settings
from src.orchestrator import THREAD_ID
from src.memory.session_logger import SessionLogger


class CommandHandler:
    """Processes /commands entered in the prompt."""

    COMMANDS = {
        "/help": "Show all available commands",
        "/auto": "Autonomous VAPT. Usage: /auto <target_url>",
        "/model": "Switch LLM model. Usage: /model ollama:qwen3:8b",
        "/mode": "Switch agent mode. Usage: /mode supervisor|single",
        "/agent": "Show which specialist agent is currently active",
        "/debug": "Toggle debug mode. Usage: /debug on|off",
        "/think": "Show/hide LLM reasoning. Usage: /think on|off",
        "/rawtools": "Show/hide raw tool output. Usage: /rawtools on|off",
        "/approval": "Toggle tool approval gate. Usage: /approval on|off",
        "/guardrails": "Toggle input guardrails. Usage: /guardrails on|off",
        "/tools": "List all available MCP tools",
        "/sessions": "Manage sessions. Usage: /sessions [list|new|load <id>|save|delete <id>]",
        "/run": "Execute a raw shell command (output injected into agent context). Usage: /run <command>",
        "/report": "Generate pentest report. Usage: /report [md|html|both]",
        "/progress": "Show VAPT phase progress and task tree",
        "/findings": "Show all findings from current session",
        "/target": "Set the target. Usage: /target <ip/url>",
        "/bg": "Background tasks. Usage: /bg [list|status <id>]",
        "/log": "View current session log. Usage: /log [tail N]",
        "/kb": "Knowledge base. Usage: /kb [status|search <query>|update]",
        "/settings": "Show current settings",
        "/clear": "Clear the screen",
        "/exit": "Exit CVA",
    }

    def __init__(self, orchestrator=None, tools=None,
                 session_store=None, task_tree=None, report_gen=None,
                 session_logger: SessionLogger = None, kb=None, recorder=None):
        self.orchestrator = orchestrator
        self.recorder = recorder
        self.tools = tools or []
        self.session_store = session_store
        self.task_tree = task_tree
        self.report_gen = report_gen
        self.kb = kb
        self.session_logger = session_logger or SessionLogger()
        self.current_session_id = None

    def is_command(self, text: str) -> bool:
        """Check if input is a slash command."""
        return text.strip().startswith("/")

    def execute(self, text: str) -> Tuple[str, Optional[str]]:
        """Execute a slash command.

        Returns:
            (output_message, action) where action can be:
            - None: just display output
            - "exit": quit the app
            - "clear": clear screen
            - "inject:<text>": inject text into agent conversation
        """
        text = text.strip()
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": lambda: (self._help(), None),
            "/auto": lambda: self._auto(args),
            "/model": lambda: (self._model(args), None),
            "/mode": lambda: (self._mode(args), None),
            "/agent": lambda: (self._agent(), None),
            "/debug": lambda: (self._debug(args), None),
            "/think": lambda: (self._think(args), None),
            "/rawtools": lambda: (self._rawtools(args), None),
            "/approval": lambda: (self._approval(args), None),
            "/guardrails": lambda: (self._guardrails(args), None),
            "/tools": lambda: (self._list_tools(), None),
            "/settings": lambda: (self._settings(), None),
            "/run": lambda: self._run(args),
            "/clear": lambda: ("", "clear"),
            "/exit": lambda: ("Goodbye!", "exit"),
            "/quit": lambda: ("Goodbye!", "exit"),
            "/sessions": lambda: (self._sessions(args), None),
            "/report": lambda: (self._report(args), None),
            "/progress": lambda: (self._progress(), None),
            "/findings": lambda: (self._findings(), None),
            "/target": lambda: (self._set_target(args), None),
            "/bg": lambda: (self._bg(args), None),
            "/log": lambda: (self._log(args), None),
            "/kb": lambda: (self._kb(args), None),
        }

        handler = handlers.get(cmd)
        if handler:
            return handler()
        return f"Unknown command: {cmd}. Type /help for available commands.", None

    def _help(self) -> str:
        lines = ["╔══ CVA Commands ══════════════════════════════════════════╗"]
        for cmd, desc in self.COMMANDS.items():
            lines.append(f"  {cmd:14s} — {desc}")
        lines.append("╚══════════════════════════════════════════════════════════╝")
        return "\n".join(lines)

    def _auto(self, args: str):
        """Run autonomous VAPT. Usage: /auto <target_url>"""
        if not args.strip():
            return "Usage: /auto <target_url> — e.g., /auto http://127.0.0.1:8080", None

        target = args.strip()
        if not target.startswith(("http://", "https://")):
            target = f"http://{target}"

        # Set the target in subsystems
        if self.task_tree:
            self.task_tree.target = target
        if self.report_gen:
            self.report_gen.target = target

        from src.auto import run_auto_from_interactive
        result = run_auto_from_interactive(
            target=target,
            tools=self.tools,
            orchestrator=self.orchestrator,
            report_gen=self.report_gen,
            session_logger=self.session_logger,
        )
        return result, None

    def _bg(self, args: str) -> str:
        """Background task management."""
        from src.auto import bg_runner

        parts = args.strip().split(maxsplit=1) if args.strip() else ["list"]
        subcmd = parts[0].lower()
        subarg = parts[1] if len(parts) > 1 else ""

        if subcmd in ("list", "ls", ""):
            tasks = bg_runner.list_tasks()
            if not tasks:
                return "No background tasks."
            lines = ["╔══ Background Tasks ══╗"]
            for t in tasks:
                status = "✓" if t["status"] == "done" else "⏳"
                lines.append(f"  {status} {t['id']:8s} {t['status']}")
            lines.append("╚══════════════════════╝")
            return "\n".join(lines)

        elif subcmd == "status":
            if not subarg:
                return "Usage: /bg status <task_id>"
            status = bg_runner.get_status(subarg)
            if status["status"] == "not_found":
                return f"Task {subarg} not found."
            output = f"Task {subarg}: {status['status']}"
            if "result" in status:
                output += f"\n{status['result'][:2000]}"
            return output

        else:
            return "Usage: /bg [list|status <task_id>]"

    def _model(self, args: str) -> str:
        if not args:
            current = f"{settings.llm_provider}:{getattr(settings, f'{settings.llm_provider}_model', settings.ollama_model)}"
            return f"Current model: {current}\nUsage: /model provider:model (e.g., /model ollama:qwen3:8b)"

        if ":" in args:
            parts = args.split(":", 1)
            provider = parts[0]
            model = parts[1]
        else:
            provider = args
            model = None

        try:
            if self.orchestrator:
                self.orchestrator.switch_model(provider, model)
            settings.llm_provider = provider
            if provider == "ollama" and model:
                settings.ollama_model = model
            return f"✓ Switched to {provider}:{model or 'default'}"
        except Exception as e:
            return f"✗ Failed to switch model: {e}"

    def _mode(self, args: str) -> str:
        if not args:
            return f"Current mode: {settings.agent_mode}\nUsage: /mode supervisor|single"
        mode = args.strip().lower()
        if mode not in ("supervisor", "single"):
            return "Usage: /mode supervisor|single"
        settings.agent_mode = mode
        if self.orchestrator:
            self.orchestrator.mode = mode
            # _build() dispatches on self.mode to _build_supervisor()/_build_single().
            self.orchestrator.graph = self.orchestrator._build()
        return f"✓ Agent mode switched to: {mode}"

    def _agent(self) -> str:
        if self.orchestrator and hasattr(self.orchestrator, 'active_agent'):
            return f"Active specialist: {self.orchestrator.active_agent}"
        return "Agent info unavailable."

    def _debug(self, args: str) -> str:
        if args.lower() in ("on", "true", "1"):
            settings.debug_mode = True
            return "✓ Debug mode ON — raw tool outputs will be shown"
        elif args.lower() in ("off", "false", "0"):
            settings.debug_mode = False
            return "✓ Debug mode OFF"
        else:
            status = "ON" if settings.debug_mode else "OFF"
            return f"Debug mode: {status}\nUsage: /debug on|off"

    def _think(self, args: str) -> str:
        if args.lower() in ("on", "true", "1", "show"):
            settings.show_thinking = True
            return "✓ Thinking display ON — LLM reasoning blocks will be shown"
        elif args.lower() in ("off", "false", "0", "hide"):
            settings.show_thinking = False
            return "✓ Thinking display OFF — reasoning runs silently"
        else:
            status = "ON" if settings.show_thinking else "OFF"
            return f"Thinking display: {status}\nUsage: /think on|off"

    def _rawtools(self, args: str) -> str:
        if args.lower() in ("on", "true", "1", "show"):
            settings.show_tool_output = True
            return "✓ Raw tool output ON — full output shown after each tool call"
        elif args.lower() in ("off", "false", "0", "hide"):
            settings.show_tool_output = False
            return "✓ Raw tool output OFF — only a brief summary shown"
        else:
            status = "ON" if settings.show_tool_output else "OFF"
            return f"Raw tool output: {status}\nUsage: /rawtools on|off"

    def _approval(self, args: str) -> str:
        if args.lower() in ("on", "true", "1", "enable"):
            settings.require_approval = True
            return "✓ Approval gate ON — every tool call will require your authorisation"
        elif args.lower() in ("off", "false", "0", "disable"):
            settings.require_approval = False
            return "✓ Approval gate OFF — tools execute automatically"
        else:
            status = "ON" if settings.require_approval else "OFF"
            return f"Tool approval gate: {status}\nUsage: /approval on|off"

    def _guardrails(self, args: str) -> str:
        if args.lower() in ("on", "true", "1", "enable"):
            settings.guardrails_enabled = True
            return "✓ Guardrails ON — input will be checked for prompt injection"
        elif args.lower() in ("off", "false", "0", "disable"):
            settings.guardrails_enabled = False
            return "✓ Guardrails OFF — no injection checks"
        else:
            status = "ON" if settings.guardrails_enabled else "OFF"
            return f"Guardrails: {status}\nUsage: /guardrails on|off"

    def _list_tools(self) -> str:
        if not self.tools:
            return "No tools loaded."

        # Group tools by category. CVA exposes generic tools — specific scanners
        # (nmap, gobuster, sqlmap, ...) are run through execute_shell_command.
        categories = {
            "Execution": ["execute_shell_command", "execute_sandboxed_script"],
            "Read": ["read_local_file"],
            "Exploit Research": ["search_exploits", "examine_exploit"],
            "Knowledge": ["search_knowledge_base"],
            "Sessions": ["create_shell_session", "send_to_session",
                         "get_session_output", "list_shell_sessions", "terminate_session"],
        }

        lines = ["╔══ Available Tools ══╗"]
        categorized = set()

        for cat, tool_names in categories.items():
            cat_tools = [t for t in self.tools if t.name in tool_names]
            if cat_tools:
                lines.append(f"\n  [{cat}]")
                for tool in cat_tools:
                    lines.append(f"    • {tool.name:28s} — {tool.description[:55]}")
                    categorized.add(tool.name)

        # Uncategorized tools (MCP or custom)
        other = [t for t in self.tools if t.name not in categorized]
        if other:
            lines.append(f"\n  [Other / MCP]")
            for tool in other:
                lines.append(f"    • {tool.name:28s} — {tool.description[:55]}")

        lines.append(f"\n╚══ {len(self.tools)} tools loaded ══╝")
        return "\n".join(lines)

    def _settings(self) -> str:
        session_info = f"  Session:    {self.current_session_id or 'none'}\n"
        target_info = f"  Target:     {self.task_tree.target if self.task_tree else 'not set'}\n"
        log_info = f"  Log file:   {self.session_logger.log_path or 'none'}\n"
        agent_info = ""
        if self.orchestrator and hasattr(self.orchestrator, 'active_agent'):
            agent_info = f"  Active:     {self.orchestrator.active_agent}\n"
        return (
            f"╔══ CVA Settings ══╗\n"
            f"  Provider:   {settings.llm_provider}\n"
            f"  Model:      {settings.ollama_model}\n"
            f"  Ollama URL: {settings.ollama_base_url}\n"
            f"  Mode:       {settings.agent_mode}\n"
            f"{agent_info}"
            f"  Debug:      {'ON' if settings.debug_mode else 'OFF'}\n"
            f"  Thinking:   {'ON' if settings.show_thinking else 'OFF'}\n"
            f"  Raw tools:  {'ON' if settings.show_tool_output else 'OFF'}\n"
            f"  Approval:   {'ON' if settings.require_approval else 'OFF'}\n"
            f"  Guardrails: {'ON' if settings.guardrails_enabled else 'OFF'}\n"
            f"{target_info}"
            f"{session_info}"
            f"{log_info}"
            f"  MongoDB:    {settings.mongo_uri}\n"
            f"╚══════════════════╝"
        )

    def _run(self, args: str) -> Tuple[str, Optional[str]]:
        """Execute a raw shell command and inject output into agent context."""
        if not args:
            return "Usage: /run <command>", None
        try:
            result = subprocess.run(
                args, shell=True, capture_output=True, text=True, timeout=120
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            output = output or "(no output)"

            # Inject into agent context so the agent knows about this command
            inject_text = f"[Manual command executed by user]\n$ {args}\n{output[:3000]}"
            return output, f"inject:{inject_text}"
        except subprocess.TimeoutExpired:
            return "Command timed out after 120 seconds.", None
        except Exception as e:
            return f"Error: {e}", None

    def _sessions(self, args: str) -> str:
        if not self.session_store:
            return "Session store not available (MongoDB may not be running)."

        parts = args.strip().split(maxsplit=1) if args.strip() else ["list"]
        subcmd = parts[0].lower()
        subarg = parts[1] if len(parts) > 1 else ""

        if subcmd in ("list", "ls", ""):
            sessions = self.session_store.list_sessions()
            if not sessions:
                return "No saved sessions. Use: /sessions new [name]"
            lines = ["╔══ Saved Sessions ══╗"]
            for s in sessions:
                name = s.get("name", "unnamed")
                sid = s["_id"]
                updated = s.get("updated_at", "")
                target = s.get("target", "")
                target_str = f" → {target}" if target else ""
                lines.append(f"  {sid}  {name:20s}{target_str}  {str(updated)[:16]}")
            lines.append("╚════════════════════╝")
            lines.append("Use: /sessions load <id> | /sessions new [name] | /sessions delete <id>")
            return "\n".join(lines)

        elif subcmd == "new":
            name = subarg or None
            sid = self.session_store.create_session(name)
            self.current_session_id = sid
            if self.recorder:
                self.recorder.session_id = sid
            self.session_logger.switch_session(sid)
            self.session_logger.log_event("session", f"New session created: {sid} ({name or 'unnamed'})")
            return f"✓ Created session: {sid} ({name or 'unnamed'})\n  Log: {self.session_logger.log_path}"

        elif subcmd == "load":
            if not subarg:
                return "Usage: /sessions load <session_id>"
            session = self.session_store.load_session(subarg)
            if not session:
                return f"Session '{subarg}' not found."
            self.current_session_id = subarg
            if self.recorder:
                self.recorder.session_id = subarg
            target = session.get("target", "")
            if target and self.task_tree:
                self.task_tree.target = target
            if target and self.report_gen:
                self.report_gen.target = target

            self.session_logger.switch_session(subarg)
            self.session_logger.log_event("session", f"Session loaded: {subarg}")

            # Restore messages into the agent's checkpointer
            saved_msgs = session.get("messages", [])
            if saved_msgs and self.orchestrator:
                from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
                restored = []
                for m in saved_msgs:
                    msg_type = m.get("type", "human")
                    content = m.get("content", "")
                    if msg_type == "human":
                        restored.append(HumanMessage(content=content))
                    elif msg_type == "ai":
                        restored.append(AIMessage(content=content))
                    elif msg_type == "system":
                        restored.append(SystemMessage(content=content))
                if restored:
                    self.orchestrator.update_messages(restored, THREAD_ID)

            msg_count = len(saved_msgs)
            return f"✓ Loaded session: {subarg} ({msg_count} messages, target: {target or 'none'})\n  Log: {self.session_logger.log_path}"

        elif subcmd == "save":
            if not self.current_session_id:
                return "No active session. Use: /sessions new"
            if self.orchestrator:
                messages = self.orchestrator.get_messages(THREAD_ID)
                self.session_store.save_messages(self.current_session_id, messages)
                if self.task_tree:
                    self.session_store.sessions.update_one(
                        {"_id": self.current_session_id},
                        {"$set": {"target": self.task_tree.target}}
                    )
            self.session_logger.log_event("session", "Session saved")
            return f"✓ Session {self.current_session_id} saved."

        elif subcmd in ("delete", "rm"):
            if not subarg:
                return "Usage: /sessions delete <session_id>"
            self.session_store.delete_session(subarg)
            if self.current_session_id == subarg:
                self.current_session_id = None
            return f"✓ Session {subarg} deleted."

        else:
            return f"Unknown sessions subcommand: {subcmd}\nUse: /sessions [list|new|load|save|delete]"

    def _report(self, args: str) -> str:
        if not self.report_gen:
            return "Report generator not available."

        fmt = args.strip().lower() or "both"
        if fmt not in ("md", "html", "both", "markdown"):
            return "Usage: /report [md|html|both]"

        try:
            # Populate from session if available
            if self.session_store and self.current_session_id:
                self.report_gen.from_session(self.session_store, self.current_session_id)

            if self.task_tree:
                self.report_gen.target = self.task_tree.target

            if self.current_session_id:
                output_dir = "reports"
                saved = self.report_gen.save(output_dir=output_dir, fmt=fmt,
                                             base_name=f"session_{self.current_session_id}")
            else:
                saved = self.report_gen.save(fmt=fmt)

            paths = "\n".join(f"  → {p}" for p in saved)
            self.session_logger.log_event("report", f"Report generated: {', '.join(saved)}")
            return f"✓ Report generated:\n{paths}\n\n  {len(self.report_gen.findings)} findings, {len(self.report_gen.raw_evidence)} evidence items."
        except Exception as e:
            return f"✗ Report generation failed: {e}"

    def _progress(self) -> str:
        if not self.task_tree:
            return "Progress tracker not available."
        return self.task_tree.get_progress()

    def _findings(self) -> str:
        if not self.task_tree:
            return "Progress tracker not available."
        return self.task_tree.get_findings_summary()

    def _set_target(self, args: str) -> str:
        if not args:
            tt = self.task_tree.target if self.task_tree else ""
            ot = getattr(self.orchestrator, "target", "") if self.orchestrator else ""
            current = tt or ot or "not set"
            return (
                f"Current target: {current}\n"
                f"Usage: /target <ip/url>"
            )

        target = args.strip().rstrip("/")
        # Normalise: add scheme if bare IP/hostname
        if target and not target.startswith(("http://", "https://")) and not target.startswith("/"):
            target = f"http://{target}"

        # Update all subsystems
        if self.task_tree:
            self.task_tree.target = target
        if self.report_gen:
            self.report_gen.target = target
        if self.orchestrator:
            self.orchestrator.set_target(target)   # injects into LLM context

        self.session_logger.log_event("target", f"Target set to: {target}")
        return (
            f"✓ Target set to: {target}\n"
            f"  The LLM has been notified. All agent prompts now include this target."
        )

    def _log(self, args: str) -> str:
        """View current session log."""
        if not self.session_logger.session_id:
            return "No active session. Use /sessions new to start one."

        tail = 50
        if args.strip():
            try:
                parts = args.strip().split()
                if parts[0].lower() == "tail" and len(parts) > 1:
                    tail = int(parts[1])
                else:
                    tail = int(parts[0])
            except (ValueError, IndexError):
                pass

        return self.session_logger.get_log_contents(tail=tail)

    def _kb(self, args: str) -> str:
        """Knowledge base management."""
        parts = args.strip().split(maxsplit=1) if args.strip() else ["status"]
        subcmd = parts[0].lower()
        subarg = parts[1] if len(parts) > 1 else ""

        if subcmd == "status":
            if not self.kb:
                return "Knowledge base not initialized."
            stats = self.kb.get_stats()
            return (
                f"╔══ Knowledge Base ══╗\n"
                f"  Backend:    {stats.get('backend', 'n/a')}\n"
                f"  Status:     {stats.get('status', 'unknown')}\n"
                f"  Documents:  {stats.get('documents', 0)}\n"
                f"  Path:       {stats.get('path', 'n/a')}\n"
                f"╚════════════════════╝"
            )

        elif subcmd == "search":
            if not subarg:
                return "Usage: /kb search <query>"
            if not self.kb or not self.kb.available:
                return "Knowledge base unavailable. Run: python scripts/ingest_kb.py"
            results = self.kb.search(subarg, limit=5)
            if not results:
                return f"No results for: {subarg}"
            lines = [f"╔══ KB Search: '{subarg}' ══╗"]
            for i, r in enumerate(results, 1):
                source = r["source"]
                section = str(r.get("section", ""))[:40]
                score = r["score"]
                text = str(r["text"])[:150].replace("\n", " ")
                lines.append(f"\n  [{i}] ({source}) {section} [score: {score:.2f}]")
                lines.append(f"      {text}...")
            lines.append(f"\n╚══ {len(results)} results ══╝")
            return "\n".join(lines)

        elif subcmd in ("update", "ingest"):
            import subprocess as sp
            try:
                result = sp.run(
                    [sys.executable, "scripts/ingest_kb.py", "--skip-clone"],
                    capture_output=True, text=True, timeout=1200,
                    cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent),
                )
                output = result.stdout[-500:] if result.stdout else ""
                if result.returncode != 0:
                    output += f"\n[stderr]: {result.stderr[-200:]}"
                return f"KB update complete:\n{output}"
            except Exception as e:
                return f"KB update failed: {e}"

        else:
            return f"Unknown /kb subcommand: {subcmd}\nUsage: /kb [status|search <query>|update]"
