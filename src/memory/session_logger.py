"""Per-Session File Logger — writes timestamped logs for all CVA actions.

Each session gets its own log file at logs/<session_id>.log.
Switching sessions switches the log file. Resuming a session appends
to the existing log.
"""

import os
from datetime import datetime, timezone
from typing import Optional


class SessionLogger:
    """File-based per-session logger for all CVA actions."""

    LOG_DIR = "logs"

    def __init__(self, session_id: Optional[str] = None):
        self._session_id = None
        self._log_path = None
        os.makedirs(self.LOG_DIR, exist_ok=True)
        if session_id:
            self.switch_session(session_id)

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def log_path(self) -> Optional[str]:
        return self._log_path

    def switch_session(self, session_id: str):
        """Switch to a new/existing session log file.

        If the file already exists, future writes append to it.
        """
        self._session_id = session_id
        self._log_path = os.path.join(self.LOG_DIR, f"{session_id}.log")
        # Write session header if file is new
        if not os.path.exists(self._log_path):
            self._write(f"{'='*60}")
            self._write(f"CVA Session Log — {session_id}")
            self._write(f"Created: {self._ts()}")
            self._write(f"{'='*60}\n")
        else:
            self._write(f"\n{'─'*60}")
            self._write(f"Session resumed: {self._ts()}")
            self._write(f"{'─'*60}\n")

    def log_user_input(self, text: str):
        """Log user input (natural language or slash commands)."""
        self._write(f"[{self._ts()}] USER: {text}")

    def log_agent_response(self, content: str, max_len: int = 500):
        """Log agent response (truncated to avoid huge log files)."""
        truncated = content[:max_len]
        if len(content) > max_len:
            truncated += f"\n  ... ({len(content) - max_len} more chars)"
        self._write(f"[{self._ts()}] AGENT: {truncated}")

    def log_tool_call(self, tool_name: str, args: dict):
        """Log a tool invocation."""
        args_str = ", ".join(f"{k}={repr(v)[:100]}" for k, v in args.items())
        self._write(f"[{self._ts()}] TOOL CALL: {tool_name}({args_str})")

    def log_tool_result(self, tool_name: str, result: str, max_len: int = 300):
        """Log a tool result (truncated)."""
        truncated = result[:max_len]
        if len(result) > max_len:
            truncated += f"\n  ... ({len(result) - max_len} more chars)"
        self._write(f"[{self._ts()}] TOOL RESULT [{tool_name}]: {truncated}")

    def log_command(self, command: str, output: str = "", max_len: int = 300):
        """Log a slash command and its output."""
        self._write(f"[{self._ts()}] COMMAND: {command}")
        if output:
            truncated = output[:max_len]
            if len(output) > max_len:
                truncated += f"\n  ... ({len(output) - max_len} more chars)"
            self._write(f"  OUTPUT: {truncated}")

    def log_finding(self, title: str, severity: str, details: str = ""):
        """Log a discovered finding."""
        self._write(f"[{self._ts()}] FINDING [{severity.upper()}]: {title}")
        if details:
            self._write(f"  DETAILS: {details[:200]}")

    def log_event(self, event_type: str, message: str):
        """Log a generic event (errors, status changes, etc.)."""
        self._write(f"[{self._ts()}] {event_type.upper()}: {message}")

    def get_log_contents(self, tail: int = 50) -> str:
        """Read the last N lines of the current log file."""
        if not self._log_path or not os.path.exists(self._log_path):
            return "No log file for current session."
        try:
            with open(self._log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if tail and len(lines) > tail:
                return "".join(lines[-tail:])
            return "".join(lines)
        except Exception as e:
            return f"Error reading log: {e}"

    def _write(self, line: str):
        """Append a line to the current log file."""
        if not self._log_path:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass  # Don't crash CVA because of a log write failure

    @staticmethod
    def _ts() -> str:
        """Current timestamp string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    @staticmethod
    def get_report_path(session_id: str) -> str:
        """Get the fixed report file path for a session.

        Using a fixed path per session means resuming a session
        updates the same report file.
        """
        os.makedirs("reports", exist_ok=True)
        return os.path.join("reports", f"session_{session_id}")
