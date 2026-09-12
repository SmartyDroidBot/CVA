"""Engagement scope — type, boundaries, and per-type methodology profiles.

Gives the agent explicit context so it runs the *right* methodology (a web app
gets web tooling, a network range gets host/port discovery) instead of a generic
one-size-fits-all plan. Inspired by the Structured Attack Tree approach
(arXiv 2509.07939): the methodology is code-owned and deterministic; the LLM
fills in the concrete commands per task.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from src.tracker.task_tree import Phase


class EngagementType(str, Enum):
    WEB = "web"
    NETWORK = "network"
    API = "api"
    HOST = "host"
    GENERIC = "generic"


# ── Type detection ────────────────────────────────────────────────────────────

_API_HINT = re.compile(r"/(api|v\d+|graphql|swagger|openapi|rest)\b", re.IGNORECASE)
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_CIDR = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}$")


def detect_type(target: str) -> EngagementType:
    """Best-effort engagement type from a target string.

    http(s):// → WEB (API when the URL looks API-shaped); IP/CIDR/bare host →
    NETWORK. HOST (privilege escalation) is opt-in via an explicit override,
    since a bare address usually means "test this host over the network".
    """
    t = (target or "").strip()
    if not t:
        return EngagementType.GENERIC
    if t.lower().startswith(("http://", "https://")):
        return EngagementType.API if _API_HINT.search(t) else EngagementType.WEB
    return EngagementType.NETWORK


def _host_of(target: str) -> str:
    """Extract the bare host from a URL or host[:port] string."""
    t = (target or "").strip()
    if not t:
        return ""
    if "://" in t:
        return (urlparse(t).hostname or "").lower()
    # strip CIDR suffix and :port
    t = t.split("/")[0]
    return t.split(":")[0].lower()


_LOOPBACK = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


# ── Scope ───────────────────────────────────────────────────────────────────

@dataclass
class Scope:
    engagement_type: EngagementType = EngagementType.GENERIC
    targets: List[str] = field(default_factory=list)       # in-scope
    out_of_scope: List[str] = field(default_factory=list)
    intensity: str = "normal"                              # safe | normal | aggressive
    objective: str = ""

    @classmethod
    def for_target(cls, target: str, engagement_type: Optional[EngagementType] = None,
                   **kw) -> "Scope":
        etype = engagement_type or detect_type(target)
        targets = [target] if target else []
        return cls(engagement_type=etype, targets=targets, **kw)

    def in_scope_hosts(self) -> set:
        hosts = {_host_of(t) for t in self.targets if _host_of(t)}
        return hosts | _LOOPBACK

    def is_command_in_scope(self, command: str) -> Tuple[bool, Optional[str]]:
        """Block commands that clearly target a host outside the in-scope set.

        Extracts URLs/IPs from the command; a target-looking host that is neither
        in scope nor loopback is out of bounds. File paths/wordlists don't match
        and are ignored. Commands with no host reference are allowed.
        """
        if not command:
            return True, None
        allowed = self.in_scope_hosts()
        # Hosts from any URLs in the command.
        candidates = set()
        for m in re.finditer(r"https?://([^/\s:'\"]+)", command, re.IGNORECASE):
            candidates.add(m.group(1).lower())
        # Bare IPv4 tokens.
        for m in _IPV4.finditer(command):
            candidates.add(m.group(0).lower())
        for host in candidates:
            if host not in allowed:
                return False, host
        return True, None

    def scope_prompt(self) -> str:
        rules = _TYPE_RULES.get(self.engagement_type, _TYPE_RULES[EngagementType.GENERIC])
        in_scope = ", ".join(self.targets) or "(none set)"
        oos = ", ".join(self.out_of_scope) or "everything not in scope"
        obj = f"\nObjective: {self.objective}" if self.objective else ""
        return (
            "## ENGAGEMENT SCOPE\n"
            f"Type: {self.engagement_type.value.upper()}\n"
            f"In-scope: {in_scope}\n"
            f"Out-of-scope: {oos}{obj}\n"
            f"Rules: {rules}\n"
            "Stay strictly within the in-scope targets — never touch other hosts."
        )


_TYPE_RULES = {
    EngagementType.WEB:
        "WEB APPLICATION test. Use HTTP/web tooling (curl, whatweb, ffuf/feroxbuster/"
        "gobuster, sqlmap, nikto). Do NOT run host/port/network scans (no nmap -sn/-sS/-sV "
        "sweeps).",
    EngagementType.API:
        "API test. Work against the API endpoints (curl, schema discovery, auth/BOLA/"
        "injection checks). Do NOT run network/port scans or web content brute-forcing "
        "unrelated to the API.",
    EngagementType.NETWORK:
        "NETWORK/INFRASTRUCTURE test. Start with host discovery and service/version scanning "
        "(nmap), then enumerate the services you find. Web tools apply only to HTTP services "
        "you actually discover.",
    EngagementType.HOST:
        "SINGLE-HOST / PRIVILEGE-ESCALATION test assuming local access. Focus on local enum "
        "and privesc (SUID/sudo/cron/kernel, linpeas/winpeas). Do NOT run external network "
        "scans.",
    EngagementType.GENERIC:
        "General VAPT. Follow standard methodology appropriate to what you discover.",
}


# ── Methodology profiles (the code-owned task templates) ───────────────────────
# Each entry: (phase, task description with tool guidance). Ordered; the engine
# instantiates them into the task graph in order.

PROFILES = {
    EngagementType.WEB: [
        (Phase.RECON, "Fingerprint the web app: HTTP headers and server/framework/tech stack "
                      "(whatweb, curl -sI). Note technologies, versions, and security headers."),
        (Phase.RECON, "Map the surface: fetch robots.txt and sitemap.xml and the main pages; "
                      "note links, forms, parameters, and referenced API endpoints."),
        (Phase.ENUM,  "Discover hidden content/endpoints via directory brute-forcing "
                      "(feroxbuster/ffuf/gobuster) with a web wordlist; record interesting paths."),
        (Phase.VULN,  "Test discovered inputs for injection: SQLi (sqlmap) and command injection "
                      "on parameters; reflected/stored XSS on inputs."),
        (Phase.VULN,  "Test authentication, sessions, and access control: default/weak creds, "
                      "IDOR/BOLA on object references, and privilege boundaries."),
        (Phase.VULN,  "Check other web flaws: SSRF, insecure file upload, and sensitive file/"
                      "information exposure or misconfiguration."),
        (Phase.EXPLOIT, "Validate and exploit each CONFIRMED web vulnerability; capture concrete "
                        "evidence (requests/responses, tokens, extracted data)."),
        (Phase.REPORT, "Summarize confirmed findings with severity, evidence, and remediation; "
                       "call record_finding for each."),
    ],
    EngagementType.API: [
        (Phase.RECON, "Discover the API surface: fetch OpenAPI/Swagger/GraphQL schema and "
                      "enumerate endpoints/methods (curl); note the auth scheme and parameters."),
        (Phase.ENUM,  "Enumerate endpoints and object identifiers; map which endpoints require "
                      "auth and what roles exist."),
        (Phase.VULN,  "Test authorization: broken object-level auth (BOLA/IDOR), broken "
                      "function-level auth (BFLA), and missing authentication."),
        (Phase.VULN,  "Test injection (SQL/NoSQL/command) on API parameters, mass assignment, "
                      "and excessive data exposure."),
        (Phase.VULN,  "Check rate limiting / resource consumption and security misconfiguration."),
        (Phase.EXPLOIT, "Validate and exploit CONFIRMED API flaws; capture request/response evidence."),
        (Phase.REPORT, "Summarize findings with severity, evidence, and remediation; "
                       "call record_finding for each."),
    ],
    EngagementType.NETWORK: [
        (Phase.RECON, "Host discovery across the in-scope target(s) (nmap -sn / ping sweep); "
                      "list live hosts."),
        (Phase.RECON, "Port and service/version scan of live hosts (nmap -sV, top ports first); "
                      "record open ports and service versions."),
        (Phase.ENUM,  "Enumerate each discovered service (SMB/FTP/SSH/SNMP/LDAP/HTTP/...) with "
                      "service-specific tools; grab banners, shares, users, and configs."),
        (Phase.VULN,  "Map service+version to known vulnerabilities (searchsploit); run nikto "
                      "against HTTP services; check for default/weak credentials."),
        (Phase.EXPLOIT, "Exploit confirmed vulnerabilities or weak credentials to gain access; "
                        "capture evidence."),
        (Phase.POST_EXPLOIT, "From any foothold, assess impact: enumerate the host and note "
                             "lateral-movement opportunities."),
        (Phase.REPORT, "Summarize findings with severity, evidence, and remediation; "
                       "call record_finding for each."),
    ],
    EngagementType.HOST: [
        (Phase.RECON, "Local situational awareness: id/whoami, OS and kernel version, users, "
                      "network interfaces, running services, and installed software."),
        (Phase.ENUM,  "Enumerate privilege-escalation vectors: sudo -l, SUID/SGID binaries, "
                      "writable cron jobs, capabilities, world-writable files, kernel version "
                      "(or run linpeas/winpeas)."),
        (Phase.EXPLOIT, "Attempt privilege escalation via the most promising vector; confirm "
                        "elevated access."),
        (Phase.POST_EXPLOIT, "Harvest credentials and sensitive data; note persistence and "
                             "lateral-movement options."),
        (Phase.REPORT, "Summarize the privesc path and findings with evidence and remediation; "
                       "call record_finding for each."),
    ],
}


def profile_for(engagement_type: EngagementType) -> List[Tuple[Phase, str]]:
    """Return the methodology template for a type (empty list for GENERIC)."""
    return PROFILES.get(engagement_type, [])
