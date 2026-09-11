"""LangChain tool that lets an agent query CVA's knowledge base mid-reasoning.

The tool resolves against whatever knowledge source is registered via
``setup_kb_tool`` — normally the merged ``DoubleRAG`` (static KB always on,
Qdrant vector KB when available). It works as long as the static KB is present,
and automatically gains semantic results once the vector store is populated.
"""

from typing import Optional

from langchain_core.tools import tool

# Set from main.py / auto.py. Any object exposing
# ``get_context(phase: str, query: str) -> str`` works (e.g. DoubleRAG).
_ACTIVE_KB = None

# Valid VAPT phases the KB understands; anything else falls back to recon.
_VALID_PHASES = {
    "reconnaissance", "enumeration", "vulnerability_analysis",
    "exploitation", "post_exploitation", "reporting",
}


def setup_kb_tool(kb):
    """Register the active knowledge source for ``search_knowledge_base``."""
    global _ACTIVE_KB
    _ACTIVE_KB = kb


@tool
def search_knowledge_base(query: str, phase: Optional[str] = None) -> str:
    """Search CVA's internal knowledge base (HackTricks, PayloadsAllTheThings,
    GTFOBins, OWASP CheatSheets) for pentesting techniques, payloads, bypasses,
    or methodology. USE THIS when you meet an unfamiliar service (e.g. Apache
    2.4.49), a new vulnerability class, or need a specific payload.

    Args:
        query: Specific question or keywords (e.g. 'Apache 2.4.49 exploit',
               'SQL injection auth bypass').
        phase: Optional VAPT phase to focus the search — one of
               reconnaissance, enumeration, vulnerability_analysis,
               exploitation, post_exploitation, reporting.
    """
    if _ACTIVE_KB is None:
        return "Knowledge base is not initialized."

    phase = phase if phase in _VALID_PHASES else "reconnaissance"
    try:
        context = _ACTIVE_KB.get_context(phase, query)
    except Exception as e:  # pragma: no cover - defensive
        return f"Knowledge base error: {e}"

    return context or f"No results found in the knowledge base for '{query}'."
