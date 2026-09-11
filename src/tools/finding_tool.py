"""The ``record_finding`` tool — lets the agent declare confirmed findings.

Explicit and reliable: the model records a structured finding the moment it
confirms one, instead of a post-hoc keyword scan of the transcript. Resolves
against a FindingRecorder registered via ``setup_finding_tool``.
"""

from langchain_core.tools import tool

_RECORDER = None


def setup_finding_tool(recorder):
    """Register the active FindingRecorder for ``record_finding``."""
    global _RECORDER
    _RECORDER = recorder


@tool
def record_finding(title: str, severity: str = "info", description: str = "",
                   evidence: str = "", remediation: str = "", category: str = "") -> str:
    """Record a CONFIRMED security finding so it appears in the pentest report.

    Call this the moment you confirm a vulnerability or notable weakness — do not
    wait until the end of the engagement.

    Args:
        title: Short finding name (e.g. "SQL Injection in /rest/search").
        severity: One of critical | high | medium | low | info.
        description: What the issue is and its impact.
        evidence: Concrete proof — the request/response, command output, or payload.
        remediation: How to fix it.
        category: Optional grouping (e.g. "Injection", "Broken Access Control").
    """
    if _RECORDER is None:
        return "Finding recorder not initialized."
    return _RECORDER.record(
        title=title, severity=severity, description=description,
        evidence=evidence, remediation=remediation, category=category,
    )
