"""Double RAG — queries both Static KB and Dynamic Session DB for context."""

from typing import List, Dict, Optional
from src.config import settings


class DoubleRAG:
    """Queries both static and dynamic knowledge sources for context enrichment."""
    
    def __init__(self, static_kb=None, session_store=None):
        self.static_kb = static_kb
        self.session_store = session_store
    
    def query(self, query_text: str, session_id: str = None, k: int = 3) -> str:
        """
        Query both knowledge bases and merge context.
        
        Returns a formatted context string to inject into the agent prompt.
        """
        context_parts = []
        
        # ── Static KB (Qdrant) ──
        if self.static_kb:
            try:
                embedding = self.static_kb._placeholder_embedding(query_text)
                static_results = self.static_kb.search(embedding, limit=k)
                if static_results and not any(r.get("category") == "error" for r in static_results):
                    context_parts.append("[STATIC KNOWLEDGE BASE]")
                    for r in static_results:
                        if r.get("score", 0) > 0.5:
                            context_parts.append(f"• [{r['category']}] {r['text'][:200]}")
            except Exception:
                pass
        
        # ── Dynamic Session DB (MongoDB) ──
        if self.session_store and session_id:
            try:
                # Get recent findings
                findings = self.session_store.get_findings(session_id)
                if findings:
                    context_parts.append("[SESSION FINDINGS]")
                    for f in findings[:5]:
                        context_parts.append(f"• {f}")
                
                # Get notes
                notes = self.session_store.get_notes(session_id)
                if notes:
                    context_parts.append("[SESSION NOTES]")
                    for n in notes[:5]:
                        context_parts.append(f"• [{n.get('category', '')}] {n.get('content', '')[:200]}")
            except Exception:
                pass
        
        if context_parts:
            return "\n".join(context_parts)
        return ""
