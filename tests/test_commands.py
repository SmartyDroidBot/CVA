"""Tests for enhanced slash commands."""

import pytest
from src.ui.commands import CommandHandler
from src.tracker.task_tree import TaskTree
from src.reporting.generator import ReportGenerator


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


class TestEnhancedCommands:
    """Tests for new slash commands."""
    
    @pytest.fixture
    def handler(self):
        tree = TaskTree(target="10.0.0.1")
        report = ReportGenerator()
        return CommandHandler(task_tree=tree, report_gen=report)
    
    def test_help_includes_new_commands(self, handler):
        output, _ = handler.execute("/help")
        assert "/report" in output
        assert "/progress" in output
        assert "/findings" in output
        assert "/target" in output
    
    def test_target_set(self, handler):
        output, _ = handler.execute("/target 192.168.1.50")
        assert "192.168.1.50" in output
        assert handler.task_tree.target == "192.168.1.50"
    
    def test_target_show(self, handler):
        output, _ = handler.execute("/target")
        assert "10.0.0.1" in output
    
    def test_progress_empty(self, handler):
        output, _ = handler.execute("/progress")
        assert "Target" in output or "10.0.0.1" in output
    
    def test_findings_empty(self, handler):
        output, _ = handler.execute("/findings")
        assert "No findings" in output or "Findings" in output
    
    def test_report_no_findings(self, handler):
        output, _ = handler.execute("/report md")
        # Should still generate a report
        assert "Report" in output or "report" in output
    
    def test_settings_shows_target(self, handler):
        output, _ = handler.execute("/settings")
        assert "Target" in output or "target" in output
    
    def test_sessions_without_store(self, handler):
        output, _ = handler.execute("/sessions")
        assert "not available" in output or "Session" in output
    
    def test_tools_categorized(self, handler):
        """Tools should be categorized when listed."""
        # Without tools it should show "No tools loaded"
        output, _ = handler.execute("/tools")
        assert "No tools loaded" in output or "tools" in output.lower()
    
    def test_unknown_command(self, handler):
        output, _ = handler.execute("/foobar")
        assert "Unknown" in output


@requires_mongo
class TestSessionCommands:
    """Tests for session management commands (requires MongoDB)."""
    
    @pytest.fixture
    def handler_with_store(self):
        from src.memory.session_store import SessionStore
        store = SessionStore()
        tree = TaskTree(target="test.com")
        handler = CommandHandler(session_store=store, task_tree=tree)
        yield handler
        store.close()
    
    def test_sessions_new(self, handler_with_store):
        output, _ = handler_with_store.execute("/sessions new test_cmd")
        assert "Created" in output
        sid = handler_with_store.current_session_id
        assert sid is not None
        # Cleanup
        handler_with_store.session_store.delete_session(sid)
    
    def test_sessions_list(self, handler_with_store):
        store = handler_with_store.session_store
        sid = store.create_session("list_test_cmd")
        output, _ = handler_with_store.execute("/sessions list")
        assert "list_test_cmd" in output or sid in output
        store.delete_session(sid)
    
    def test_sessions_load_and_delete(self, handler_with_store):
        store = handler_with_store.session_store
        sid = store.create_session("load_test_cmd")
        
        output, _ = handler_with_store.execute(f"/sessions load {sid}")
        assert "Loaded" in output
        assert handler_with_store.current_session_id == sid
        
        output2, _ = handler_with_store.execute(f"/sessions delete {sid}")
        assert "deleted" in output2
