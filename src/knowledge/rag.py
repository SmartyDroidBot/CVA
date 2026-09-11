"""KnowledgeService — merges one or more KnowledgeSource backends.

Callers depend only on this service plus the KnowledgeSource contract, never on
a concrete backend. Today it wraps a single FTS5 source; adding a vector/hybrid
source later means constructing the service with more sources — nothing else
changes. ``DoubleRAG`` remains as a backward-compatible alias.
"""

from typing import List, Optional

from src.knowledge.base import Hit, KnowledgeSource


class KnowledgeService:
    """Aggregates knowledge sources for context enrichment and search."""

    def __init__(self, sources: Optional[List[KnowledgeSource]] = None):
        self.sources: List[KnowledgeSource] = [s for s in (sources or []) if s is not None]

    def get_context(self, phase: str, query: str = "") -> str:
        parts = []
        for src in self.sources:
            try:
                if getattr(src, "available", False):
                    ctx = src.get_context(phase, query)
                    if ctx:
                        parts.append(ctx)
            except Exception:
                continue
        return "\n\n".join(parts)

    def search(self, query: str, phase: Optional[str] = None,
               limit: int = 5) -> List[Hit]:
        hits: List[Hit] = []
        for src in self.sources:
            try:
                if getattr(src, "available", False):
                    hits.extend(src.search(query, phase=phase, limit=limit))
            except Exception:
                continue
        return hits[:limit] if limit else hits

    @property
    def available(self) -> bool:
        return any(getattr(s, "available", False) for s in self.sources)

    def get_stats(self) -> dict:
        return {
            "available": self.available,
            "sources": [s.get_stats() for s in self.sources],
        }


# Backward-compatible name used by earlier code paths.
DoubleRAG = KnowledgeService
