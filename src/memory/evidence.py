"""Structured finding capture.

The ``record_finding`` tool writes here: the agent explicitly declares confirmed
findings, which are added to the in-memory report and (when a session store is
present) persisted for /report and ReportGenerator.from_session. This replaces
the old keyword-guessing extractor.
"""

from typing import Callable, List, Optional

from src.reporting.generator import Finding


class FindingRecorder:
    """Collects structured findings and fans them out to report + session store."""

    def __init__(self, report_gen=None, session_store=None,
                 session_id: Optional[str] = None,
                 on_record: Optional[Callable] = None):
        self.report_gen = report_gen
        self.session_store = session_store
        self.session_id = session_id
        self.on_record = on_record
        self.findings: List[Finding] = []

    def record(self, title: str, severity: str = "info", description: str = "",
               evidence: str = "", remediation: str = "", category: str = "",
               tool: str = "CVA") -> str:
        if not title:
            return "A finding requires a title."
        sev = (severity or "info").lower()
        if sev not in Finding.SEVERITIES:
            sev = "info"
        finding = Finding(
            title=title, severity=sev, description=description, evidence=evidence,
            remediation=remediation, tool=tool, category=category or title,
        )
        # De-dupe by (title, severity) so repeated calls don't inflate the report.
        if any(f.title == finding.title and f.severity == finding.severity
               for f in self.findings):
            return f"Finding already recorded: {title}"
        self.findings.append(finding)

        if self.report_gen is not None:
            try:
                self.report_gen.add_finding(finding)
            except Exception:
                pass
        if self.session_store is not None and self.session_id:
            try:
                self.session_store.save_finding(self.session_id, finding.to_dict())
            except Exception:
                pass
        if self.on_record:
            try:
                self.on_record(finding)
            except Exception:
                pass
        return f"Recorded {sev.upper()} finding: {title}"
