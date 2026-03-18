"""Vector Knowledge Base — Qdrant-backed semantic search for pentesting knowledge.

Uses nomic-embed-text via Ollama for query embedding and Qdrant for
similarity search with optional phase filtering.
"""

import os
import requests
from typing import List, Dict, Optional

from src.config import settings


class VectorKB:
    """Semantic search over the ingested pentesting knowledge base."""

    def __init__(self):
        self._client = None
        self._collection = getattr(settings, "kb_collection", "cva_kb")
        self._embed_model = getattr(settings, "embedding_model", "nomic-embed-text")
        self._ollama_url = settings.ollama_base_url
        self._available = False
        self._connect()

    def _connect(self):
        """Lazily connect to Qdrant."""
        try:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=5,
            )
            # Check if collection exists
            collections = [c.name for c in self._client.get_collections().collections]
            if self._collection in collections:
                self._available = True
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def _embed_query(self, text: str) -> Optional[List[float]]:
        """Embed a query string using Ollama."""
        try:
            resp = requests.post(
                f"{self._ollama_url}/api/embed",
                json={"model": self._embed_model, "input": text},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            emb = data.get("embeddings", [data.get("embedding", [])])
            if isinstance(emb[0], list):
                return emb[0]
            return emb
        except Exception:
            return None

    def search(self, query: str, phase: str = None, limit: int = 5) -> List[Dict]:
        """Semantic search over the KB.

        Args:
            query: Natural language search query.
            phase: Optional VAPT phase filter.
            limit: Number of results.

        Returns:
            List of {text, source, file, section, phase, score} dicts.
        """
        if not self._available:
            return []

        vector = self._embed_query(query)
        if not vector:
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            search_filter = None
            if phase and phase != "general":
                search_filter = Filter(
                    must=[FieldCondition(key="phase", match=MatchValue(value=phase))]
                )

            results_resp = self._client.query_points(
                collection_name=self._collection,
                query=vector,
                query_filter=search_filter,
                limit=limit,
            )
            results = results_resp.points

            return [
                {
                    "text": r.payload.get("text", ""),
                    "source": r.payload.get("source", ""),
                    "file": r.payload.get("file", ""),
                    "section": r.payload.get("section", ""),
                    "phase": r.payload.get("phase", ""),
                    "score": r.score,
                }
                for r in results
            ]
        except Exception:
            return []

    def get_phase_knowledge(self, phase: str, limit: int = 3) -> str:
        """Get top knowledge entries for a specific VAPT phase.

        Uses a generic query per phase to pull the most relevant chunks.
        """
        phase_queries = {
            "reconnaissance": "network scanning recon OSINT subdomain discovery nmap",
            "enumeration": "service enumeration directory brute force web enumeration",
            "vulnerability_analysis": "vulnerability assessment web vulnerability OWASP injection",
            "exploitation": "exploitation payload reverse shell metasploit SQL injection",
            "post_exploitation": "privilege escalation lateral movement persistence post exploitation",
            "reporting": "pentest report findings evidence remediation",
        }
        query = phase_queries.get(phase, f"{phase} pentesting techniques")
        results = self.search(query, phase=phase, limit=limit)
        if not results:
            return ""

        lines = [f"[KNOWLEDGE — {phase.replace('_', ' ').title()}]"]
        for r in results:
            source = r["source"]
            section = r["section"]
            header = f"({source}" + (f": {section}" if section else "") + ")"
            lines.append(f"\n### {header}")
            lines.append(r["text"][:800])
        return "\n".join(lines)

    def get_context_for_agent(self, phase: str, query: str = "") -> str:
        """Get combined knowledge for agent prompt injection.

        Performs both phase-based retrieval and query-specific search.
        """
        if not self._available:
            return ""

        parts = []

        # Phase-specific knowledge
        phase_kb = self.get_phase_knowledge(phase, limit=2)
        if phase_kb:
            parts.append(phase_kb)

        # Query-specific search (cross-phase)
        if query and len(query.strip()) > 3:
            hits = self.search(query, limit=3)
            extras = []
            for hit in hits:
                if hit["score"] > 0.3:  # Only include reasonably relevant results
                    source = hit["source"]
                    section = hit["section"]
                    header = f"({source}" + (f": {section}" if section else "") + ")"
                    extras.append(f"### {header}\n{hit['text'][:600]}")
            if extras:
                parts.append("[RELEVANT KNOWLEDGE]\n" + "\n\n".join(extras))

        return "\n\n".join(parts)

    def get_stats(self) -> Dict:
        """Get collection statistics."""
        if not self._available:
            return {"status": "unavailable", "points": 0}
        try:
            info = self._client.get_collection(self._collection)
            return {
                "status": "ready",
                "points": info.points_count,
                "vectors_count": getattr(info, 'indexed_vectors_count', info.points_count),
                "collection": self._collection,
            }
        except Exception as e:
            return {"status": f"error: {e}", "points": 0}
