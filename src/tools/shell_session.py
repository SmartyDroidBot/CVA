"""Interactive Shell Sessions — PTY-based persistent sessions for stateful tools.

Inspired by CAI's ShellSession. Supports long-running interactive tools like
netcat, Metasploit, nmap, and reverse shells that persist across tool calls.
"""

import os
import pty
import signal
import select
import subprocess
import threading
import time
import uuid
from typing import Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import create_model


# ── Session Manager ──────────────────────────────────────────────────────────

ACTIVE_SESSIONS: Dict[str, "ShellSession"] = {}
_FRIENDLY_MAP: Dict[str, str] = {}     # S1 -> real_id
_REVERSE_MAP: Dict[str, str] = {}      # real_id -> S1
_COUNTER = 0


class ShellSession:
    """A persistent interactive shell session backed by a PTY."""

    def __init__(self, command: str, session_id: str = None, cwd: str = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.command = command
        self.cwd = cwd or os.getcwd()
        self.friendly_id: Optional[str] = None
        self.created_at = time.time()
        self.last_activity = time.time()

        self.process: Optional[subprocess.Popen] = None
        self.master: Optional[int] = None
        self.slave: Optional[int] = None
        self.output_buffer: List[str] = []
        self.is_running = False

    def start(self) -> Optional[str]:
        """Start the session. Returns error string on failure, None on success."""
        try:
            self.master, self.slave = pty.openpty()
            self.process = subprocess.Popen(
                self.command,
                shell=True,
                stdin=self.slave,
                stdout=self.slave,
                stderr=self.slave,
                cwd=self.cwd,
                preexec_fn=os.setsid,
                universal_newlines=True,
            )
            self.is_running = True
            self.output_buffer.append(
                f"[Session {self.session_id}] Started: {self.command}"
            )
            threading.Thread(target=self._read_output, daemon=True).start()
            return None
        except Exception as e:
            self.is_running = False
            return f"Error starting session: {e}"

    def _read_output(self):
        """Background thread reading PTY output into buffer."""
        try:
            while self.is_running and self.master is not None:
                if self.process and self.process.poll() is not None:
                    # Drain remaining output
                    try:
                        while True:
                            ready, _, _ = select.select([self.master], [], [], 0.1)
                            if not ready:
                                break
                            data = os.read(self.master, 4096).decode("utf-8", errors="replace")
                            if data:
                                self.output_buffer.append(data)
                            else:
                                break
                    except Exception:
                        pass
                    self.is_running = False
                    break

                try:
                    ready, _, _ = select.select([self.master], [], [], 0.5)
                    if not ready:
                        continue
                    data = os.read(self.master, 4096).decode("utf-8", errors="replace")
                    if data:
                        self.output_buffer.append(data)
                        self.last_activity = time.time()
                    elif self.process and self.process.poll() is not None:
                        self.is_running = False
                        break
                except Exception:
                    self.is_running = False
                    break

                time.sleep(0.05)
        except Exception as e:
            self.output_buffer.append(f"[Session read error] {e}")
            self.is_running = False

    def send_input(self, data: str) -> str:
        """Send input to the session PTY."""
        if not self.is_running:
            if self.process and self.process.poll() is None:
                self.is_running = True
            else:
                return "Session is not running."

        if self.master is None:
            return "Session PTY not available."

        try:
            encoded = (data.rstrip() + "\n").encode()
            os.write(self.master, encoded)
            self.last_activity = time.time()
            return "Input sent."
        except Exception as e:
            return f"Error sending input: {e}"

    def get_output(self, clear: bool = True) -> str:
        """Get buffered output, optionally clearing the buffer."""
        output = "\n".join(self.output_buffer)
        if clear:
            self.output_buffer = []
        return output

    def terminate(self) -> str:
        """Terminate the session and clean up resources."""
        self.is_running = False
        if self.process:
            try:
                pgid = os.getpgid(self.process.pid)
                os.killpg(pgid, signal.SIGTERM)
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait(timeout=2)
                except Exception:
                    pass
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

        for fd in (self.master, self.slave):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.master = None
        self.slave = None
        return f"Session {self.friendly_id or self.session_id} terminated."


# ── Public API (called by tool wrappers) ─────────────────────────────────────

def _resolve_id(identifier: str) -> Optional[str]:
    """Resolve S1/#1/1/'last'/raw_id to the real session_id."""
    if not identifier:
        return None
    s = str(identifier).strip()

    if s.lower() == "last":
        if not ACTIVE_SESSIONS:
            return None
        return max(ACTIVE_SESSIONS, key=lambda k: ACTIVE_SESSIONS[k].created_at)

    # Normalise S1/#1/1 -> S1
    key = s
    if s.startswith("#"):
        key = f"S{s[1:]}"
    elif s.isdigit():
        key = f"S{s}"
    elif s.upper().startswith("S") and s[1:].isdigit():
        key = s.upper()

    if s in ACTIVE_SESSIONS:
        return s
    if key in _FRIENDLY_MAP:
        return _FRIENDLY_MAP[key]
    return None


def create_session(command: str) -> str:
    """Create and start a new persistent shell session.

    Returns:
        A description string with the session ID.
    """
    global _COUNTER
    session = ShellSession(command)
    err = session.start()
    if err:
        return f"Failed: {err}"

    _COUNTER += 1
    friendly = f"S{_COUNTER}"
    session.friendly_id = friendly
    ACTIVE_SESSIONS[session.session_id] = session
    _FRIENDLY_MAP[friendly] = session.session_id
    _REVERSE_MAP[session.session_id] = friendly
    # Wait briefly for initial output
    time.sleep(0.5)
    return (
        f"Session {friendly} ({session.session_id}) started: {command}\n"
        f"Use send_to_session('{friendly}', '<input>') to interact, "
        f"get_session_output('{friendly}') to read output."
    )


def send_to(session_id: str, data: str) -> str:
    """Send input to an active session."""
    resolved = _resolve_id(session_id)
    if not resolved or resolved not in ACTIVE_SESSIONS:
        return f"Session '{session_id}' not found. Use list_shell_sessions() to see active sessions."
    return ACTIVE_SESSIONS[resolved].send_input(data)


def get_output(session_id: str) -> str:
    """Get output from an active session."""
    resolved = _resolve_id(session_id)
    if not resolved or resolved not in ACTIVE_SESSIONS:
        return f"Session '{session_id}' not found."
    sess = ACTIVE_SESSIONS[resolved]
    # Wait briefly for latest output
    time.sleep(0.3)
    output = sess.get_output(clear=True)
    status = "running" if sess.is_running else "finished"
    return f"[Session {sess.friendly_id} — {status}]\n{output}" if output else f"[Session {sess.friendly_id} — {status}] No new output."


def list_sessions() -> str:
    """List all active shell sessions."""
    # Clean up dead sessions
    dead = [sid for sid, s in ACTIVE_SESSIONS.items() if not s.is_running]
    for sid in dead:
        friendly = _REVERSE_MAP.pop(sid, None)
        if friendly:
            _FRIENDLY_MAP.pop(friendly, None)
        ACTIVE_SESSIONS.pop(sid, None)

    if not ACTIVE_SESSIONS:
        return "No active sessions."

    lines = ["Active sessions:"]
    for sid, sess in ACTIVE_SESSIONS.items():
        elapsed = int(time.time() - sess.created_at)
        lines.append(
            f"  {sess.friendly_id:4s} | {sess.command[:50]:50s} | "
            f"{'running' if sess.is_running else 'stopped':8s} | {elapsed}s"
        )
    return "\n".join(lines)


def terminate(session_id: str) -> str:
    """Terminate a session by friendly or real ID."""
    resolved = _resolve_id(session_id)
    if not resolved or resolved not in ACTIVE_SESSIONS:
        return f"Session '{session_id}' not found."
    sess = ACTIVE_SESSIONS.pop(resolved)
    friendly = _REVERSE_MAP.pop(resolved, None)
    if friendly:
        _FRIENDLY_MAP.pop(friendly, None)
    return sess.terminate()


def shutdown_all():
    """Clean up all sessions on exit."""
    for sess in list(ACTIVE_SESSIONS.values()):
        sess.terminate()
    ACTIVE_SESSIONS.clear()
    _FRIENDLY_MAP.clear()
    _REVERSE_MAP.clear()


# ── LangChain tool wrappers ─────────────────────────────────────────────────

def get_session_tools() -> list:
    """Return LangChain StructuredTools for shell session management."""
    return [
        StructuredTool.from_function(
            func=create_session,
            name="create_shell_session",
            description=(
                "Start a persistent interactive shell session (e.g., for nmap, "
                "netcat listeners, Metasploit, or any long-running command). "
                "The session runs in the background and you can interact with it "
                "through send_to_session and get_session_output."
            ),
            args_schema=create_model("CreateSessionInput", command=(str, ...)),
        ),
        StructuredTool.from_function(
            func=send_to,
            name="send_to_session",
            description=(
                "Send input/command to an active shell session (e.g., S1 or 'last'). "
                "Use this to interact with Metasploit, netcat, or any interactive process."
            ),
            args_schema=create_model(
                "SendToSessionInput",
                session_id=(str, ...),
                data=(str, ...),
            ),
        ),
        StructuredTool.from_function(
            func=get_output,
            name="get_session_output",
            description=(
                "Read new output from an active shell session. Returns the output "
                "accumulated since the last read."
            ),
            args_schema=create_model(
                "GetSessionOutputInput", session_id=(str, ...)
            ),
        ),
        StructuredTool.from_function(
            func=list_sessions,
            name="list_shell_sessions",
            description="List all active persistent shell sessions with their IDs and status.",
            args_schema=create_model("ListSessionsInput"),
        ),
        StructuredTool.from_function(
            func=terminate,
            name="terminate_session",
            description="Terminate a persistent shell session by ID (e.g., S1 or 'last').",
            args_schema=create_model(
                "TerminateSessionInput", session_id=(str, ...)
            ),
        ),
    ]
