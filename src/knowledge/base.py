"""Knowledge-source abstraction — the decoupling contract for CVA's KB.

Any retrieval backend implements ``KnowledgeSource``. Today that is the lexical
``FTS5KnowledgeBase``; a vector or hybrid backend can be added later purely by
writing another class that satisfies this Protocol and selecting it via the
``kb_backend`` setting — no caller (kb_tool, main, commands, engine) changes.

A "Hit" is a plain dict so it crosses module boundaries without coupling:
    {"source": str, "section": str, "phase": str, "score": float, "text": str}
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable

Hit = Dict[str, object]

VALID_PHASES = {
    "reconnaissance", "enumeration", "vulnerability_analysis",
    "exploitation", "post_exploitation", "reporting",
}


@runtime_checkable
class KnowledgeSource(Protocol):
    """Contract every knowledge backend must satisfy."""

    @property
    def available(self) -> bool:
        """True when this source can actually answer queries."""
        ...

    def search(self, query: str, phase: Optional[str] = None,
               limit: int = 5) -> List[Hit]:
        """Return up to ``limit`` ranked hits, optionally filtered by phase."""
        ...

    def get_context(self, phase: str, query: str = "") -> str:
        """Return a formatted context string for prompt injection / the KB tool."""
        ...

    def get_stats(self) -> Dict:
        """Return a small status dict (backend, document count, ...)."""
        ...


def format_hits(hits: List[Hit]) -> str:
    """Render hits into the context string the KB tool and prompts expect."""
    if not hits:
        return ""
    out = []
    for h in hits:
        header = f"[{h.get('source', 'kb')}"
        section = h.get("section")
        if section:
            header += f": {section}"
        header += "]"
        out.append(f"{header}\n{h.get('text', '')}\n")
    return "\n---\n".join(out)
