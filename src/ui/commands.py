"""Slash command handler for CVA CLI — enhanced with reporting, progress, sessions."""

import subprocess
from typing import Optional, Tuple
from src.config import settings


class CommandHandler:
    """Processes /commands entered in the prompt."""
    
    COMMANDS = {
        "/help": "Show all available commands",
        "/model": "Switch LLM model. Usage: /model ollama:qwen3:8b",
        "/debug": "Toggle debug mode. Usage: /debug on|off",
        "/tools": "List all available MCP tools",
        "/sessions": "Manage sessions. Usage: /sessions [list|new|load <id>|save|delete <id>]",
        "/run": "Execute a raw shell command. Usage: /run <command>",
        "/report": "Generate pentest report. Usage: /report [md|html|both]",
        "/progress": "Show VAPT phase progress and task tree",
        "/findings": "Show all findings from current session",
        "/target": "Set the target. Usage: /target <ip/url>",
        "/settings": "Show current settings",
        "/clear": "Clear the screen",
        "/exit": "Exit CVA",
    }
    
    def __init__(self, orchestrator=None, tools=None,
                 session_store=None, task_tree=None, report_gen=None):
        self.orchestrator = orchestrator
        self.tools = tools or []
        self.session_store = session_store
        self.task_tree = task_tree
        self.report_gen = report_gen
        self.current_session_id = None
    
    def is_command(self, text: str) -> bool:
        """Check if input is a slash command."""
        return text.strip().startswith("/")
    
    def execute(self, text: str) -> Tuple[str, Optional[str]]:
        """
        Execute a slash command.
        
        Returns:
            (output_message, action) where action can be:
            - None: just display output
            - "exit": quit the app
            - "clear": clear screen
            - "run_result": output is a raw command result for parser
        """
        text = text.strip()
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        handlers = {
            "/help": lambda: (self._help(), None),
            "/model": lambda: (self._model(args), None),
            "/debug": lambda: (self._debug(args), None),
            "/tools": lambda: (self._list_tools(), None),
            "/settings": lambda: (self._settings(), None),
            "/run": lambda: (self._run(args), "run_result"),
            "/clear": lambda: ("", "clear"),
            "/exit": lambda: ("Goodbye!", "exit"),
            "/quit": lambda: ("Goodbye!", "exit"),
            "/sessions": lambda: (self._sessions(args), None),
            "/report": lambda: (self._report(args), None),
            "/progress": lambda: (self._progress(), None),
            "/findings": lambda: (self._findings(), None),
            "/target": lambda: (self._set_target(args), None),
        }
        
        handler = handlers.get(cmd)
        if handler:
            return handler()
        return f"Unknown command: {cmd}. Type /help for available commands.", None
    
    def _help(self) -> str:
        lines = ["╔══ CVA Commands ══╗"]
        for cmd, desc in self.COMMANDS.items():
            lines.append(f"  {cmd:12s} — {desc}")
        lines.append("╚══════════════════╝")
        return "\n".join(lines)
    
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
    
    def _list_tools(self) -> str:
        if not self.tools:
            return "No tools loaded."
        
        # Group tools by category
        categories = {
            "Recon": ["nmap_scan", "whatweb_scan", "curl_request"],
            "Enumeration": ["gobuster_dir", "ffuf_fuzz"],
            "Vulnerability": ["nikto_scan", "search_exploitdb"],
            "Exploitation": ["sqlmap_scan", "hydra_bruteforce", "execute_sandboxed_script"],
            "Research": ["search_web"],
            "Utility": ["execute_shell_command", "hash_identify"],
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
        
        # Uncategorized tools
        other = [t for t in self.tools if t.name not in categorized]
        if other:
            lines.append(f"\n  [Other]")
            for tool in other:
                lines.append(f"    • {tool.name:28s} — {tool.description[:55]}")
        
        lines.append(f"\n╚══ {len(self.tools)} tools loaded ══╝")
        return "\n".join(lines)
    
    def _settings(self) -> str:
        session_info = f"  Session:    {self.current_session_id or 'none'}\n"
        target_info = f"  Target:     {self.task_tree.target if self.task_tree else 'not set'}\n"
        return (
            f"╔══ CVA Settings ══╗\n"
            f"  Provider:   {settings.llm_provider}\n"
            f"  Model:      {settings.ollama_model}\n"
            f"  Ollama URL: {settings.ollama_base_url}\n"
            f"  Debug:      {'ON' if settings.debug_mode else 'OFF'}\n"
            f"{target_info}"
            f"{session_info}"
            f"  MongoDB:    {settings.mongo_uri}\n"
            f"  Qdrant:     {settings.qdrant_host}:{settings.qdrant_port}\n"
            f"  Sandbox:    {'enabled' if settings.sandbox_enabled else 'disabled'}\n"
            f"╚══════════════════╝"
        )
    
    def _run(self, args: str) -> str:
        if not args:
            return "Usage: /run <command>"
        try:
            result = subprocess.run(
                args, shell=True, capture_output=True, text=True, timeout=120
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out after 120 seconds."
        except Exception as e:
            return f"Error: {e}"
    
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
            return f"✓ Created session: {sid} ({name or 'unnamed'})"
        
        elif subcmd == "load":
            if not subarg:
                return "Usage: /sessions load <session_id>"
            session = self.session_store.load_session(subarg)
            if not session:
                return f"Session '{subarg}' not found."
            self.current_session_id = subarg
            target = session.get("target", "")
            if target and self.task_tree:
                self.task_tree.target = target
            msg_count = len(session.get("messages", []))
            return f"✓ Loaded session: {subarg} ({msg_count} messages, target: {target or 'none'})"
        
        elif subcmd == "save":
            if not self.current_session_id:
                return "No active session. Use: /sessions new"
            if self.orchestrator:
                messages = self.orchestrator.get_messages()
                self.session_store.save_messages(self.current_session_id, messages)
                if self.task_tree:
                    from pymongo import MongoClient
                    self.session_store.sessions.update_one(
                        {"_id": self.current_session_id},
                        {"$set": {"target": self.task_tree.target}}
                    )
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
            
            saved = self.report_gen.save(fmt=fmt)
            paths = "\n".join(f"  → {p}" for p in saved)
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
            target = self.task_tree.target if self.task_tree else "not set"
            return f"Current target: {target}\nUsage: /target <ip/url>"
        
        if self.task_tree:
            self.task_tree.target = args.strip()
        if self.report_gen:
            self.report_gen.target = args.strip()
        return f"✓ Target set to: {args.strip()}"
