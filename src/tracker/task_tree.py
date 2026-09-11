"""Pentesting Task Tree — tracks VAPT phase progress and findings."""

from datetime import datetime, timezone
from typing import List, Dict, Optional
from enum import Enum


class Phase(str, Enum):
    """Standard VAPT phases."""
    RECON = "reconnaissance"
    ENUM = "enumeration"
    VULN = "vulnerability_analysis"
    EXPLOIT = "exploitation"
    POST_EXPLOIT = "post_exploitation"
    REPORT = "reporting"


PHASE_ICONS = {
    Phase.RECON: "🔍", Phase.ENUM: "📋", Phase.VULN: "⚠️",
    Phase.EXPLOIT: "💥", Phase.POST_EXPLOIT: "🏴", Phase.REPORT: "📝",
}

PHASE_ORDER = list(Phase)

# Map the real MCP tool names to VAPT phases. The two generic tools
# (execute_shell_command, read_local_file) carry no inherent phase — their phase
# is inferred from the command string (see infer_phase_from_command) or kept
# sticky at the current phase.
TOOL_PHASE_MAP = {
    "search_exploits": Phase.VULN,
    "examine_exploit": Phase.VULN,
    "execute_sandboxed_script": Phase.EXPLOIT,
    # Shell sessions are usually opened for exploitation/interactive work.
    "create_shell_session": Phase.EXPLOIT,
}

# Keyword → phase inference for generic shell commands. Ordered most-specific
# first so offensive tooling wins over the broad recon keywords (curl/wget).
COMMAND_PHASE_KEYWORDS = [
    (Phase.ENUM, ("gobuster", "ffuf", "feroxbuster", "dirb", "dirsearch",
                  "wfuzz", "enum4linux", "smbclient", "snmpwalk", "ldapsearch")),
    (Phase.VULN, ("nikto", "sqlmap", "nuclei", "wpscan", "searchsploit")),
    (Phase.EXPLOIT, ("hydra", "medusa", "msfconsole", "metasploit",
                     "hashcat", "john ")),
    (Phase.POST_EXPLOIT, ("linpeas", "winpeas", "mimikatz", "sudo -l",
                          "secretsdump", "crackmapexec", "evil-winrm")),
    (Phase.RECON, ("nmap", "masscan", "whatweb", "whois", "dnsrecon",
                   "amass", "subfinder", "dig ", "host ", "curl", "wget")),
]


def infer_phase_from_command(command: str) -> Optional["Phase"]:
    """Best-effort VAPT phase for a raw shell command. Returns None if unknown."""
    if not command:
        return None
    low = command.lower()
    for phase, keywords in COMMAND_PHASE_KEYWORDS:
        if any(kw in low for kw in keywords):
            return phase
    return None


class TaskNode:
    """A single task/action in the pentest tree."""
    
    def __init__(self, action: str, tool: str = "", phase: Phase = Phase.RECON,
                 status: str = "pending", result_summary: str = ""):
        self.action = action
        self.tool = tool
        self.phase = phase
        self.status = status  # pending, running, done, skipped
        self.result_summary = result_summary
        self.timestamp = datetime.now(timezone.utc)
        self.children: List[TaskNode] = []
    
    def to_dict(self) -> dict:
        return {
            "action": self.action, "tool": self.tool,
            "phase": self.phase.value, "status": self.status,
            "result_summary": self.result_summary,
            "timestamp": self.timestamp.isoformat(),
            "children": [c.to_dict() for c in self.children],
        }


TASK_STATUSES = ("pending", "running", "done", "skipped", "failed")


class Task:
    """A node in the Penetration Task Graph (DAG).

    Unlike ``TaskNode`` (a record of a completed action), a ``Task`` is planned
    work with dependencies and a lifecycle, driven by the planner/executor.
    """

    def __init__(self, task_id: str, description: str, phase: Phase = Phase.RECON,
                 deps: Optional[List[str]] = None, status: str = "pending"):
        self.id = task_id
        self.description = description
        self.phase = phase
        self.deps: List[str] = list(deps or [])
        self.status = status  # one of TASK_STATUSES
        self.result = ""
        self.created = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "phase": self.phase.value, "deps": self.deps,
            "status": self.status, "result": self.result,
        }


class TaskTree:
    """Tracks pentest progress: a log of completed actions plus a task-graph DAG."""

    def __init__(self, target: str = ""):
        self.target = target
        self.nodes: List[TaskNode] = []                 # completed-action log
        self.current_phase: Phase = Phase.RECON
        self.phase_completions: Dict[Phase, bool] = {p: False for p in Phase}
        self.tasks: Dict[str, Task] = {}                # the DAG (id -> Task)
        self._task_counter = 0
    
    def add_action(self, action: str, tool: str = "", result_summary: str = "",
                   command: str = ""):
        """Add a completed action to the tree.

        Phase is chosen from (in order): the command string (for generic shell
        tools), the tool→phase map, then the current sticky phase.
        """
        phase = infer_phase_from_command(command)
        if phase is None:
            phase = TOOL_PHASE_MAP.get(tool, self.current_phase)
        node = TaskNode(
            action=action, tool=tool, phase=phase,
            status="done", result_summary=result_summary,
        )
        self.nodes.append(node)
        self.current_phase = phase
        return node
    
    def advance_phase(self, phase: Phase):
        """Manually advance to a new phase."""
        self.phase_completions[self.current_phase] = True
        self.current_phase = phase
    
    def get_progress(self) -> str:
        """Generate a text progress display."""
        lines = [f"🎯 Target: {self.target}", ""]
        
        # Phase progress bar
        for phase in PHASE_ORDER:
            icon = PHASE_ICONS[phase]
            phase_nodes = [n for n in self.nodes if n.phase == phase]
            count = len(phase_nodes)
            
            if phase == self.current_phase:
                marker = "▶"
                style = "ACTIVE"
            elif count > 0:
                marker = "✓"
                style = "DONE"
            else:
                marker = "○"
                style = ""
            
            phase_name = phase.value.replace("_", " ").title()
            lines.append(f"  {marker} {icon} {phase_name:25s} ({count} actions) {style}")
        
        # Recent actions
        lines.append(f"\n📋 Recent Actions ({len(self.nodes)} total):")
        for node in self.nodes[-8:]:
            icon = PHASE_ICONS.get(node.phase, "•")
            tool_str = f" [{node.tool}]" if node.tool else ""
            summary = f" → {node.result_summary[:60]}" if node.result_summary else ""
            lines.append(f"  {icon}{tool_str} {node.action[:50]}{summary}")
        
        return "\n".join(lines)
    
    def get_findings_summary(self) -> str:
        """Get a summary of all findings from the tree."""
        lines = [f"📊 Findings Summary for {self.target}", ""]
        
        by_phase = {}
        for node in self.nodes:
            phase = node.phase.value.replace("_", " ").title()
            if phase not in by_phase:
                by_phase[phase] = []
            if node.result_summary:
                by_phase[phase].append(f"  • {node.result_summary[:80]}")
        
        for phase, findings in by_phase.items():
            lines.append(f"\n{phase}:")
            lines.extend(findings[:10])
        
        if not by_phase:
            lines.append("  No findings recorded yet.")
        
        return "\n".join(lines)
    
    def get_status_line(self) -> str:
        """One-line status for UI display (not injected into agent prompt)."""
        phase = self.current_phase.value.replace('_', ' ').title()
        return f"Target: {self.target or 'not set'} | Phase: {phase} | Actions: {len(self.nodes)}"
    
    def get_context_for_agent(self) -> str:
        """Compact progress snapshot to inject into an agent's prompt.

        Returns an empty string when nothing has happened yet, so callers can
        cheaply skip injecting empty context.
        """
        if not self.nodes and not self.tasks:
            return ""

        phase = self.current_phase.value.replace("_", " ").title()
        lines = [
            "## PENTEST PROGRESS",
            f"Target: {self.target or 'not set'}",
            f"Current phase: {phase}",
            f"Actions so far: {len(self.nodes)}",
        ]
        if self.nodes:
            lines.append("Recent actions:")
            for node in self.nodes[-5:]:
                tool_str = f" [{node.tool}]" if node.tool else ""
                summary = f" → {node.result_summary[:80]}" if node.result_summary else ""
                lines.append(f"  - {node.action[:60]}{tool_str}{summary}")
        if self.tasks:
            lines.append("Task graph:")
            for t in self.tasks.values():
                dep_str = f" (needs {', '.join(t.deps)})" if t.deps else ""
                lines.append(f"  [{t.status}] {t.id}: {t.description[:60]}{dep_str}")
        return "\n".join(lines)

    # ── Task graph (DAG) ────────────────────────────────────────────────────

    def add_task(self, description: str, phase: Phase = Phase.RECON,
                 deps: Optional[List[str]] = None, task_id: Optional[str] = None) -> Task:
        """Add a planned task to the graph. Auto-assigns an id when not given."""
        if task_id is None:
            self._task_counter += 1
            task_id = f"t{self._task_counter}"
        task = Task(task_id=task_id, description=description, phase=phase, deps=deps)
        self.tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def ready_tasks(self) -> List[Task]:
        """Pending tasks whose dependencies are all satisfied (done)."""
        ready = []
        for t in self.tasks.values():
            if t.status != "pending":
                continue
            if all(
                (self.tasks.get(d) is not None and self.tasks[d].status == "done")
                for d in t.deps
            ):
                ready.append(t)
        return ready

    def mark(self, task_id: str, status: str, result: str = "") -> Optional[Task]:
        """Update a task's status (and optionally its result)."""
        if status not in TASK_STATUSES:
            raise ValueError(f"invalid task status: {status}")
        t = self.tasks.get(task_id)
        if not t:
            return None
        t.status = status
        if result:
            t.result = result
        if status == "running":
            self.current_phase = t.phase   # graph-driven phase progression
        return t

    def all_tasks(self) -> List[Task]:
        return list(self.tasks.values())

    def tasks_complete(self) -> bool:
        """True when there are tasks and none remain pending/running."""
        return bool(self.tasks) and all(
            t.status in ("done", "skipped", "failed") for t in self.tasks.values()
        )

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "current_phase": self.current_phase.value,
            "nodes": [n.to_dict() for n in self.nodes],
            "tasks": [t.to_dict() for t in self.tasks.values()],
        }
