"""Static Knowledge Base — Qdrant vector store for security docs."""

from typing import List, Optional, Dict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import hashlib
import uuid

from src.config import settings


class StaticKB:
    """Qdrant-based vector store for static security knowledge."""
    
    COLLECTION = "security_docs"
    VECTOR_SIZE = 384  # For all-MiniLM-L6-v2 or similar small embedding model
    
    def __init__(self):
        self.client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Create collection if it doesn't exist."""
        try:
            collections = self.client.get_collections().collections
            names = [c.name for c in collections]
            if self.COLLECTION not in names:
                self.client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=VectorParams(size=self.VECTOR_SIZE, distance=Distance.COSINE),
                )
        except Exception:
            pass  # Qdrant may not be running — fail gracefully
    
    def add_document(self, text: str, metadata: Dict = None, embedding: List[float] = None):
        """Add a document to the knowledge base."""
        if embedding is None:
            # Placeholder — in production, use an embedding model
            embedding = self._placeholder_embedding(text)
        
        point_id = str(uuid.uuid4())
        self.client.upsert(
            collection_name=self.COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "text": text,
                        "category": (metadata or {}).get("category", "general"),
                        **(metadata or {}),
                    }
                )
            ]
        )
        return point_id
    
    def search(self, query_embedding: List[float], limit: int = 5) -> List[Dict]:
        """Search the knowledge base by vector similarity."""
        try:
            results = self.client.query_points(
                collection_name=self.COLLECTION,
                query=query_embedding,
                limit=limit,
            ).points
            
            return [
                {
                    "text": r.payload.get("text", ""),
                    "category": r.payload.get("category", ""),
                    "score": r.score,
                }
                for r in results
            ]
        except Exception as e:
            return [{"text": f"Static KB search error: {e}", "category": "error", "score": 0}]
    
    def get_stats(self) -> Dict:
        """Get collection stats."""
        try:
            info = self.client.get_collection(self.COLLECTION)
            return {
                "collection": self.COLLECTION,
                "points_count": info.points_count,
                "status": str(info.status),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _placeholder_embedding(self, text: str) -> List[float]:
        """Generate a deterministic placeholder embedding from text hash.
        Replace with real embedding model in production.
        """
        h = hashlib.sha384(text.encode()).digest()
        return [float(b) / 255.0 for b in h[:self.VECTOR_SIZE]]
