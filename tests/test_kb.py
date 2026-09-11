"""Tests for the FTS5 knowledge base and the KnowledgeService merger.

Uses only stdlib sqlite3 (FTS5), so it runs anywhere without external services.
"""

import pytest

from src.knowledge.fts_kb import FTS5KnowledgeBase, build_index
from src.knowledge.rag import KnowledgeService
from src.knowledge.base import KnowledgeSource, format_hits


FIXTURE_DOCS = [
    {"source": "hacktricks", "section": "SQL Injection", "phase": "vulnerability_analysis",
     "text": "SQL injection lets an attacker inject SQL via unsanitized parameters. "
             "Use sqlmap to automate detection and exploitation of SQLi."},
    {"source": "payloads", "section": "XSS", "phase": "vulnerability_analysis",
     "text": "Cross-site scripting (XSS) injects JavaScript into a page. Try "
             "<script>alert(1)</script> in reflected parameters."},
    {"source": "hacktricks", "section": "Nmap", "phase": "reconnaissance",
     "text": "Nmap performs port scanning and service version detection. "
             "nmap -sV --open enumerates open ports on the host."},
    {"source": "gtfobins", "section": "find", "phase": "post_exploitation",
     "text": "The find binary can be abused for privilege escalation via sudo "
             "to spawn a root shell."},
]


@pytest.fixture
def kb(tmp_path):
    db = tmp_path / "kb.sqlite3"
    n = build_index(str(db), FIXTURE_DOCS)
    assert n == len(FIXTURE_DOCS)
    return FTS5KnowledgeBase(str(db))


def test_available(kb):
    assert kb.available is True
    stats = kb.get_stats()
    assert stats["backend"] == "fts5"
    assert stats["documents"] == len(FIXTURE_DOCS)


def test_missing_db_is_unavailable(tmp_path):
    kb = FTS5KnowledgeBase(str(tmp_path / "does_not_exist.sqlite3"))
    assert kb.available is False
    assert kb.search("sql injection") == []
    assert kb.get_context("vulnerability_analysis", "sqli") == ""


def test_search_finds_relevant(kb):
    hits = kb.search("sql injection", limit=5)
    assert hits, "expected at least one hit"
    # The SQL-injection doc should rank first (lowest bm25 score).
    assert "SQL" in str(hits[0]["section"]) or "sql" in str(hits[0]["text"]).lower()


def test_phase_filter(kb):
    hits = kb.search("scan ports host", phase="reconnaissance", limit=5)
    assert hits
    assert all(h["phase"] == "reconnaissance" for h in hits)


def test_query_sanitization_no_crash(kb):
    # Special FTS5 operators / punctuation must not raise or break the query.
    for q in ['"; DROP TABLE docs; --', "sql-injection AND (xss)", "***", "  ", "a"]:
        result = kb.search(q, limit=3)
        assert isinstance(result, list)


def test_get_context_formats_hits(kb):
    ctx = kb.get_context("vulnerability_analysis", "sql injection")
    assert "hacktricks" in ctx
    assert "SQL injection" in ctx


def test_get_context_empty_query_uses_phase(kb):
    # No query → seed from the phase name; should still surface recon content.
    ctx = kb.get_context("reconnaissance", "")
    assert "nmap" in ctx.lower() or "port" in ctx.lower()


def test_satisfies_protocol(kb):
    assert isinstance(kb, KnowledgeSource)


def test_format_hits_empty():
    assert format_hits([]) == ""


def test_knowledge_service_merges(kb):
    svc = KnowledgeService([kb])
    assert svc.available is True
    assert svc.search("xss", limit=3)
    assert "XSS" in svc.get_context("vulnerability_analysis", "xss")


def test_knowledge_service_empty():
    svc = KnowledgeService([])
    assert svc.available is False
    assert svc.search("anything") == []
    assert svc.get_context("reconnaissance", "x") == ""
