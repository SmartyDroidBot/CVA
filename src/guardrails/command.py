"""Output Command Guardrails — validate commands the agent wants to execute.

Catches dangerous patterns in LLM-generated shell commands before execution.
Inspired by CAI's command_execution_guardrail.
"""

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class CommandCheckResult:
    """Result of an output command guardrail check."""
    is_safe: bool
    triggers: List[str] = field(default_factory=list)
    severity: str = "info"  # info, warning, blocked

    @property
    def summary(self) -> str:
        if self.is_safe:
            return "Command passed safety check."
        return f"[{self.severity.upper()}] triggers: {', '.join(self.triggers)}"


# (regex, category, severity)
_COMMAND_PATTERNS = [
    # Destructive filesystem
    (re.compile(r"rm\s+-[rf]{2,}\s+/(?:\s|$|;)"), "rm_rf_root", "blocked"),
    (re.compile(r"mkfs\.|dd\s+if=.+of=/dev/sd"), "disk_wipe", "blocked"),
    # Fork bomb
    (re.compile(r":\(\)\s*\{"), "fork_bomb", "blocked"),
    # Reverse shell to attacker (outbound connect)
    (re.compile(r"(?:bash|sh|nc|ncat)\s.*-e\s+/bin/(?:ba)?sh"), "reverse_shell_pipe", "warning"),
    (re.compile(r"/dev/tcp/\d"), "dev_tcp_connect", "warning"),
    # Encoded payloads piped to shell
    (re.compile(r"base64\s+-d\s*\|\s*(?:bash|sh|python|perl)"), "b64_decode_to_shell", "blocked"),
    (re.compile(r"base32\s+-d\s*\|\s*(?:bash|sh)"), "b32_decode_to_shell", "blocked"),
    # Curl/wget to shell
    (re.compile(r"curl\s+\S+\s*\|\s*(?:bash|sh|python)"), "curl_pipe_shell", "warning"),
    (re.compile(r"wget\s+\S+\s*-O\s*-\s*\|\s*(?:bash|sh)"), "wget_pipe_shell", "warning"),
    # Crontab manipulation
    (re.compile(r"crontab\s+-r(?:\s|$)"), "crontab_remove", "warning"),
    # Iptables flush (destroys firewall)
    (re.compile(r"iptables\s+-F"), "iptables_flush", "warning"),
    # Disable security features
    (re.compile(r"setenforce\s+0|apparmor_parser\s+-R"), "security_disable", "warning"),
    # Password changes
    (re.compile(r"passwd\s+(?:root|--stdin)"), "password_change", "warning"),
    # Shutdown/reboot
    (re.compile(r"(?:shutdown|reboot|init\s+[06]|poweroff)(?:\s|$)"), "system_halt", "blocked"),
]


def check_command(command: str) -> CommandCheckResult:
    """Check a shell command for dangerous patterns.

    Args:
        command: The shell command string to validate.

    Returns:
        CommandCheckResult with is_safe=False if blocked-level triggers found.
    """
    if not command:
        return CommandCheckResult(is_safe=True)

    triggers = []
    max_severity = "info"
    severity_rank = {"info": 0, "warning": 1, "blocked": 2}

    for pattern, category, severity in _COMMAND_PATTERNS:
        if pattern.search(command):
            triggers.append(category)
            if severity_rank[severity] > severity_rank[max_severity]:
                max_severity = severity

    is_safe = max_severity != "blocked"

    return CommandCheckResult(
        is_safe=is_safe,
        triggers=triggers,
        severity=max_severity,
    )
