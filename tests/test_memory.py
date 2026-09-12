"""Tests for Memory module — session store and summarizer."""

import pytest
from src.memory.session_store import SessionStore


def _mongo_available() -> bool:
    try:
        from pymongo import MongoClient
        from src.config import settings
        MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=800).server_info()
        return True
    except Exception:
        return False


requires_mongo = pytest.mark.skipif(
    not _mongo_available(), reason="MongoDB not available"
)


@requires_mongo
class TestSessionStore:
    """Tests for MongoDB session persistence."""

    @pytest.fixture
    def store(self):
        """Create a session store and clean up after."""
        s = SessionStore()
        yield s
        s.close()
    
    def test_create_session(self, store):
        """Should create a session with a valid ID."""
        sid = store.create_session("test_session")
        assert sid is not None
        assert len(sid) == 8
        # Cleanup
        store.delete_session(sid)
    
    def test_save_and_load_messages(self, store):
        """Should save and load messages."""
        sid = store.create_session("test_msgs")
        
        messages = [
            {"type": "human", "content": "Scan target.test"},
            {"type": "ai", "content": "Running nmap scan..."},
        ]
        store.save_messages(sid, messages)
        
        session = store.load_session(sid)
        assert session is not None
        assert len(session["messages"]) == 2
        assert session["messages"][0]["content"] == "Scan target.test"
        
        # Cleanup
        store.delete_session(sid)
    
    def test_list_sessions(self, store):
        """Should list sessions."""
        sid = store.create_session("list_test")
        sessions = store.list_sessions()
        assert len(sessions) > 0
        
        # Cleanup
        store.delete_session(sid)
    
    def test_save_finding(self, store):
        """Should save and retrieve findings."""
        sid = store.create_session("findings_test")
        
        store.save_finding(sid, {
            "type": "open_port",
            "port": 80,
            "service": "http",
            "version": "Apache 2.4.49",
        })
        
        findings = store.get_findings(sid)
        assert len(findings) == 1
        assert findings[0]["port"] == 80
        
        # Cleanup
        store.delete_session(sid)
    
    def test_save_note(self, store):
        """Should save and retrieve notes from intelligent parser."""
        sid = store.create_session("notes_test")
        
        store.save_note(sid, "credentials", "admin:password123")
        notes = store.get_notes(sid)
        assert len(notes) == 1
        assert notes[0]["category"] == "credentials"
        
        # Cleanup
        store.delete_session(sid)
    
    def test_delete_session(self, store):
        """Should delete session and all related data."""
        sid = store.create_session("delete_test")
        store.save_finding(sid, {"type": "test"})
        store.save_note(sid, "test", "test content")
        
        store.delete_session(sid)
        
        assert store.load_session(sid) is None
        assert len(store.get_findings(sid)) == 0
        assert len(store.get_notes(sid)) == 0


class TestSummarizer:
    """Tests for context summarizer."""
    
    def test_should_summarize_threshold(self):
        """Should trigger summarization past threshold."""
        from src.memory.summarizer import Summarizer
        from src.config import settings
        
        summarizer = Summarizer()
        
        # Below threshold
        short_msgs = [{"type": "human", "content": f"msg {i}"} for i in range(5)]
        assert summarizer.should_summarize(short_msgs) is False
        
        # Above threshold
        long_msgs = [{"type": "human", "content": f"msg {i}"} for i in range(settings.max_messages_before_summary + 5)]
        assert summarizer.should_summarize(long_msgs) is True
