"""Double RAG — merges Vector KB knowledge and Dynamic Session context.

Queries both the Qdrant-backed vector knowledge base and the session's
accumulated findings/notes to produce enriched context for the agent prompt.
"""

from typing import Optional

try:
    from src.knowledge.vector_kb import VectorKB
except ImportError:
    VectorKB = None


class DoubleRAG:
    """Merges semantic pentesting knowledge with dynamic session context."""

    def __init__(self, vector_kb=None, session_store=None):
        self.vector_kb = vector_kb
        self.session_store = session_store

    def get_context(
        self,
        phase: str,
        user_query: str = "",
        session_id: str = None,
    ) -> str:
        """Build enriched context string for the agent prompt.

        Args:
            phase: Current VAPT phase (e.g. 'recon', 'exploitation').
            user_query: The user's current input (for semantic matching).
            session_id: Active session ID for dynamic context.

        Returns:
            A combined context string to prepend to agent input.
        """
        parts = []

        # ── Vector KB Knowledge (semantic search) ──
        if self.vector_kb and self.vector_kb.available:
            kb_ctx = self.vector_kb.get_context_for_agent(phase, user_query)
            if kb_ctx:
                parts.append(kb_ctx)

        # ── Dynamic Session Context ──
        if self.session_store and session_id:
            dyn_ctx = self._get_session_context(session_id)
            if dyn_ctx:
                parts.append(dyn_ctx)

        return "\n\n".join(parts)

    def _get_session_context(self, session_id: str) -> str:
        """Extract prioritized session context from MongoDB."""
        lines = []

        try:
            # Findings (most important)
            findings = self.session_store.get_findings(session_id)
            if findings:
                lines.append("[SESSION FINDINGS]")
                for f in findings[:10]:
                    sev = f.get("severity", "info")
                    title = f.get("title", f.get("type", "finding"))
                    details = f.get("description", f.get("details", ""))[:150]
                    lines.append(f"• [{sev.upper()}] {title}: {details}")

            # Notes (tool outputs, parsed data)
            notes = self.session_store.get_notes(session_id)
            if notes:
                lines.append("[SESSION NOTES]")
                for n in notes[:8]:
                    cat = n.get("category", "")
                    content = n.get("content", "")[:200]
                    lines.append(f"• [{cat}] {content}")

            # Session summary (if available)
            session = self.session_store.load_session(session_id)
            if session and session.get("summary"):
                lines.insert(0, f"[SESSION SUMMARY]\n{session['summary'][:500]}")

        except Exception:
            pass

        return "\n".join(lines)
