"""FTS5 lexical knowledge base — SQLite full-text search over the corpus.

Zero external services: the index is a single SQLite file built by
``scripts/ingest_kb.py``. Implements the ``KnowledgeSource`` contract from
``src.knowledge.base`` so it is interchangeable with any future backend.
"""

import os
import re
import sqlite3
from typing import Dict, Iterable, List, Optional

from src.knowledge.base import Hit, VALID_PHASES, format_hits

# Schema shared by the builder and reader. `docs` holds the rows; `docs_fts` is
# an external-content FTS5 index over the text column (rowid == docs.id).
_SCHEMA = """
CREATE TABLE docs (
    id      INTEGER PRIMARY KEY,
    source  TEXT,
    section TEXT,
    phase   TEXT,
    text    TEXT
);
CREATE VIRTUAL TABLE docs_fts USING fts5(
    text, content='docs', content_rowid='id', tokenize='porter unicode61'
);
"""

# When a caller asks for phase context with no query, seed retrieval with
# phase-representative keywords rather than the bare phase name (which rarely
# appears verbatim in the corpus).
_PHASE_SEEDS = {
    "reconnaissance": "reconnaissance scanning port service enumeration dns whois",
    "enumeration": "enumeration directory brute force smb ldap services",
    "vulnerability_analysis": "vulnerability injection xss sqli ssrf idor",
    "exploitation": "exploit payload reverse shell metasploit",
    "post_exploitation": "privilege escalation lateral movement persistence credentials",
    "reporting": "report remediation cvss evidence",
}


def build_index(db_path: str, docs: Iterable[Dict]) -> int:
    """(Re)build the FTS5 index at ``db_path`` from an iterable of doc dicts.

    Each doc: {source, section, phase, text}. Returns the number indexed.
    """
    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        n = 0
        for d in docs:
            text = (d.get("text") or "").strip()
            if not text:
                continue
            cur = conn.execute(
                "INSERT INTO docs(source, section, phase, text) VALUES (?,?,?,?)",
                (d.get("source", ""), d.get("section", ""), d.get("phase", ""), text),
            )
            conn.execute(
                "INSERT INTO docs_fts(rowid, text) VALUES (?, ?)",
                (cur.lastrowid, text),
            )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


class FTS5KnowledgeBase:
    """Read-only lexical KB over the FTS5 index."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self):
        try:
            if os.path.exists(self.db_path):
                # read-only, shareable across the app's threads
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        except Exception:
            self._conn = None

    # ── KnowledgeSource contract ──────────────────────────────────────────────

    @property
    def available(self) -> bool:
        if not self._conn:
            return False
        try:
            return self._conn.execute("SELECT count(*) FROM docs").fetchone()[0] > 0
        except Exception:
            return False

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Turn free text into a safe FTS5 MATCH string.

        Extract word-ish tokens (dropping FTS operators like - " * : ( ) ) and
        OR-join them as quoted terms so punctuation can never break the query.
        """
        tokens = re.findall(r"[A-Za-z0-9_.+#/-]+", query or "")
        tokens = [t.strip("-./") for t in tokens]
        tokens = [t for t in tokens if len(t) > 1][:12]
        if not tokens:
            return ""
        return " OR ".join(f'"{t}"' for t in tokens)

    def search(self, query: str, phase: Optional[str] = None,
               limit: int = 5) -> List[Hit]:
        if not self.available:
            return []
        match = self._sanitize_query(query)
        if not match:
            return []
        sql = (
            "SELECT d.source, d.section, d.phase, bm25(docs_fts) AS score, d.text "
            "FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid "
            "WHERE docs_fts MATCH ?"
        )
        params: List[object] = [match]
        if phase:
            sql += " AND d.phase = ?"
            params.append(phase)
        sql += " ORDER BY score LIMIT ?"   # bm25: lower score = more relevant
        params.append(limit)
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except Exception:
            return []
        return [
            {"source": r[0], "section": r[1], "phase": r[2],
             "score": r[3], "text": r[4]}
            for r in rows
        ]

    def get_context(self, phase: str, query: str = "") -> str:
        # With no query, seed retrieval with phase-representative keywords so
        # prompt injection still surfaces phase-relevant methodology.
        effective_query = query or _PHASE_SEEDS.get(phase, (phase or "").replace("_", " "))
        phase_filter = phase if phase in VALID_PHASES else None
        hits = self.search(effective_query, phase=phase_filter, limit=4)
        # If a phase filter starved the results, retry unfiltered.
        if not hits and phase_filter and query:
            hits = self.search(query, phase=None, limit=4)
        return format_hits(hits)

    def get_stats(self) -> Dict:
        if not self._conn:
            return {"backend": "fts5", "status": "missing",
                    "documents": 0, "path": self.db_path}
        try:
            n = self._conn.execute("SELECT count(*) FROM docs").fetchone()[0]
            return {"backend": "fts5", "status": "ready" if n else "empty",
                    "documents": n, "path": self.db_path}
        except Exception:
            return {"backend": "fts5", "status": "unavailable",
                    "documents": 0, "path": self.db_path}
