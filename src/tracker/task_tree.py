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

# Map tool names to VAPT phases
TOOL_PHASE_MAP = {
    "nmap_scan": Phase.RECON, "gobuster_dir": Phase.ENUM,
    "nikto_scan": Phase.VULN, "sqlmap_scan": Phase.EXPLOIT,
    "hydra_bruteforce": Phase.EXPLOIT, "whatweb_scan": Phase.RECON,
    "ffuf_fuzz": Phase.ENUM, "curl_request": Phase.RECON,
    "search_exploitdb": Phase.VULN, "search_web": Phase.RECON,
    # execute_shell_command is generic — phase is inferred from current_phase
    "execute_sandboxed_script": Phase.EXPLOIT,
    "hash_identify": Phase.POST_EXPLOIT,
    # Shell sessions
    "create_shell_session": Phase.EXPLOIT,
}


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


class TaskTree:
    """Tracks the pentesting progress as a tree of actions."""
    
    def __init__(self, target: str = ""):
        self.target = target
        self.nodes: List[TaskNode] = []
        self.current_phase: Phase = Phase.RECON
        self.phase_completions: Dict[Phase, bool] = {p: False for p in Phase}
    
    def add_action(self, action: str, tool: str = "", result_summary: str = ""):
        """Add a completed action to the tree."""
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
        if not self.nodes:
            return ""

        phase = self.current_phase.value.replace("_", " ").title()
        lines = [
            "## PENTEST PROGRESS",
            f"Target: {self.target or 'not set'}",
            f"Current phase: {phase}",
            f"Actions so far: {len(self.nodes)}",
            "Recent actions:",
        ]
        for node in self.nodes[-5:]:
            tool_str = f" [{node.tool}]" if node.tool else ""
            summary = f" → {node.result_summary[:80]}" if node.result_summary else ""
            lines.append(f"  - {node.action[:60]}{tool_str}{summary}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "current_phase": self.current_phase.value,
            "nodes": [n.to_dict() for n in self.nodes],
        }
