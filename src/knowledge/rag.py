"""Double RAG — combines static KB (always on) + vector KB (optional).

FIXED: StaticKB is now always injected regardless of Qdrant availability.
Previously, RAG context was empty when Qdrant wasn't running.
"""

from typing import Optional
from src.knowledge.static_kb import StaticKB
from src.knowledge.vector_kb import VectorKB


class DoubleRAG:
    """Merges static and vector knowledge for agent context enrichment.

    Static KB is always available and provides baseline pentesting knowledge.
    Vector KB adds deeper semantic search when Qdrant is running.
    """

    def __init__(self, vector_kb: Optional[VectorKB] = None):
        self.static_kb = StaticKB()
        self.vector_kb = vector_kb

    def get_context(self, phase: str, query: str = "") -> str:
        """Get combined RAG context for a given phase and query.

        Always includes static KB. Adds vector KB results when available.
        """
        parts = []

        # Static KB — always available, zero infrastructure cost
        # StaticKB exposes get_context_for_agent(phase, query)
        static_ctx = self.static_kb.get_context_for_agent(phase, query)
        if static_ctx:
            parts.append(static_ctx)

        # Vector KB — optional, requires Qdrant
        if self.vector_kb and self.vector_kb.available:
            vector_ctx = self.vector_kb.get_context_for_agent(phase, query)
            if vector_ctx:
                parts.append(vector_ctx)

        return "\n\n".join(parts)

    @property
    def available(self) -> bool:
        """True if at least static KB is available (always True now)."""
        return True

    @property
    def vector_available(self) -> bool:
        """True if Qdrant vector KB is also available."""
        return self.vector_kb is not None and self.vector_kb.available
