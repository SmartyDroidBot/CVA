"""LangChain tool wrapper for searching the Vector KB during an agent's reasoning loop."""

from langchain_core.tools import tool
from typing import Optional

# We will initialize these from main.py
_ACTIVE_KB = None

def setup_kb_tool(vector_kb):
    """Sets the active VectorKB instance for the tool to resolve."""
    global _ACTIVE_KB
    _ACTIVE_KB = vector_kb

@tool
def search_knowledge_base(query: str, phase: Optional[str] = None) -> str:
    """Search the internal CVA semantic knowledge base for pentesting techniques,
    payloads, bypasses, or methodology. USE THIS whenever you discover a new service (e.g., Apache 2.4.49),
    a new vulnerability, or when you are stuck or need a specific payload!

    Args:
        query: The specific question or keywords (e.g. 'Apache 2.4.49 exploits', 'SQL injection bypass')
        phase: (Optional) Limit search to a specific phase: 'reconnaissance', 'enumeration',
               'vulnerability_analysis', 'exploitation', 'post_exploitation', 'reporting'.
    """
    if not _ACTIVE_KB or not _ACTIVE_KB.available:
        return "Knowledge base is currently unavailable or not initialized."
    
    hits = _ACTIVE_KB.search(query, phase=phase, limit=4)
    if not hits:
        return f"No results found in the knowledge base for '{query}'."

    results = []
    for hit in hits:
        source = hit["source"]
        section = hit["section"]
        score = hit["score"]
        header = f"[{source}" + (f": {section}" if section else "") + f"] (score: {score:.2f})"
        content = hit["text"]
        results.append(f"{header}\n{content}\n")

    return "\n---\n".join(results)
