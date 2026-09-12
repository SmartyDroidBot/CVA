"""Tests for the structured finding recorder and the record_finding tool."""

import pytest

from src.memory.evidence import FindingRecorder
from src.reporting.generator import ReportGenerator, Finding
from src.tools.finding_tool import setup_finding_tool, record_finding


class FakeStore:
    def __init__(self):
        self.saved = []

    def save_finding(self, session_id, finding):
        self.saved.append((session_id, finding))


def test_record_adds_to_report_and_findings():
    rg = ReportGenerator()
    rec = FindingRecorder(report_gen=rg)
    msg = rec.record("SQL Injection in /search", severity="critical",
                     evidence="' OR 1=1 --", remediation="Use parameterized queries")
    assert "critical" in msg.lower()
    assert len(rec.findings) == 1
    assert rec.findings[0].severity == "critical"
    assert len(rg.findings) == 1
    assert rg.findings[0].title == "SQL Injection in /search"


def test_record_persists_to_session_store():
    store = FakeStore()
    rec = FindingRecorder(session_store=store, session_id="s1")
    rec.record("XSS", severity="high")
    assert len(store.saved) == 1
    sid, data = store.saved[0]
    assert sid == "s1"
    assert data["title"] == "XSS" and data["severity"] == "high"


def test_record_dedupes_by_title_and_severity():
    rg = ReportGenerator()
    rec = FindingRecorder(report_gen=rg)
    rec.record("IDOR", severity="high")
    rec.record("IDOR", severity="high")   # duplicate
    assert len(rec.findings) == 1
    assert len(rg.findings) == 1


def test_invalid_severity_defaults_to_info():
    rec = FindingRecorder()
    rec.record("Odd thing", severity="catastrophic")
    assert rec.findings[0].severity == "info"


def test_empty_title_rejected():
    rec = FindingRecorder()
    out = rec.record("", severity="high")
    assert "requires a title" in out
    assert rec.findings == []


def test_on_record_callback_fires():
    seen = []
    rec = FindingRecorder(on_record=lambda f: seen.append(f.title))
    rec.record("Path Traversal", severity="high")
    assert seen == ["Path Traversal"]


def test_record_finding_tool_routes_to_recorder():
    rg = ReportGenerator()
    rec = FindingRecorder(report_gen=rg)
    setup_finding_tool(rec)
    out = record_finding.invoke({
        "title": "Auth bypass", "severity": "critical",
        "evidence": "logged in as admin without creds",
    })
    assert "Auth bypass" in out
    assert rec.findings and rec.findings[0].title == "Auth bypass"


def test_recorded_finding_appears_in_report():
    rg = ReportGenerator()
    rg.target = "http://t"
    rec = FindingRecorder(report_gen=rg)
    rec.record("SSRF", severity="high", evidence="fetched the internal metadata endpoint")
    md = rg.generate_markdown()
    assert "SSRF" in md
