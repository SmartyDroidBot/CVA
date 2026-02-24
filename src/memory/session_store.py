"""MongoDB Session Store — persists sessions for stop/resume."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pymongo import MongoClient
from pymongo.collection import Collection
import uuid
import json

from src.config import settings


class SessionStore:
    """CRUD operations for CVA sessions in MongoDB."""
    
    def __init__(self):
        self.client = MongoClient(settings.mongo_uri)
        self.db = self.client[settings.mongo_db]
        self.sessions: Collection = self.db["sessions"]
        self.findings: Collection = self.db["findings"]
        self.notes: Collection = self.db["notes"]
    
    def create_session(self, name: str = None) -> str:
        """Create a new session. Returns session_id."""
        session_id = str(uuid.uuid4())[:8]
        self.sessions.insert_one({
            "_id": session_id,
            "name": name or f"session_{session_id}",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "messages": [],
            "summary": "",
            "target": "",
            "status": "active",
        })
        return session_id
    
    def save_messages(self, session_id: str, messages: List[Dict[str, Any]]):
        """Save serialized messages to a session."""
        serialized = []
        for msg in messages:
            if hasattr(msg, "type"):
                # LangChain message object
                serialized.append({
                    "type": msg.type,
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                    "name": getattr(msg, "name", None),
                })
            elif isinstance(msg, dict):
                serialized.append(msg)
        
        self.sessions.update_one(
            {"_id": session_id},
            {
                "$set": {
                    "messages": serialized,
                    "updated_at": datetime.now(timezone.utc),
                }
            }
        )
    
    def load_session(self, session_id: str) -> Optional[Dict]:
        """Load a session by ID."""
        return self.sessions.find_one({"_id": session_id})
    
    def list_sessions(self) -> List[Dict]:
        """List all sessions, newest first."""
        return list(self.sessions.find(
            {},
            {"_id": 1, "name": 1, "created_at": 1, "updated_at": 1, "status": 1, "target": 1}
        ).sort("updated_at", -1).limit(20))
    
    def update_summary(self, session_id: str, summary: str):
        """Update the session summary (from summarizer agent)."""
        self.sessions.update_one(
            {"_id": session_id},
            {"$set": {"summary": summary, "updated_at": datetime.now(timezone.utc)}}
        )
    
    def save_finding(self, session_id: str, finding: Dict[str, Any]):
        """Save a structured finding (port, service, vulnerability, etc.)."""
        finding["session_id"] = session_id
        finding["timestamp"] = datetime.now(timezone.utc)
        self.findings.insert_one(finding)
    
    def get_findings(self, session_id: str) -> List[Dict]:
        """Get all findings for a session."""
        return list(self.findings.find(
            {"session_id": session_id},
            {"_id": 0}
        ).sort("timestamp", -1))
    
    def save_note(self, session_id: str, category: str, content: str):
        """Save a parsed note/evidence from intelligent parser."""
        self.notes.insert_one({
            "session_id": session_id,
            "category": category,
            "content": content,
            "timestamp": datetime.now(timezone.utc),
        })
    
    def get_notes(self, session_id: str) -> List[Dict]:
        """Get all notes for a session."""
        return list(self.notes.find(
            {"session_id": session_id},
            {"_id": 0}
        ).sort("timestamp", -1))
    
    def delete_session(self, session_id: str):
        """Delete a session and its findings."""
        self.sessions.delete_one({"_id": session_id})
        self.findings.delete_many({"session_id": session_id})
        self.notes.delete_many({"session_id": session_id})
    
    def close(self):
        """Close MongoDB connection."""
        self.client.close()
