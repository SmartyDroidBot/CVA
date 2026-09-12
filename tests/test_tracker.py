"""Tests for Task Tree / Progress Tracker module."""

import pytest
from src.tracker.task_tree import (
    TaskTree, Phase, TaskNode, TOOL_PHASE_MAP, infer_phase_from_command,
)


class TestTaskTree:
    """Tests for VAPT progress tracking."""
    
    def test_create_tree(self):
        tree = TaskTree(target="target.test")
        assert tree.target == "target.test"
        assert tree.current_phase == Phase.RECON
        assert len(tree.nodes) == 0
    
    def test_add_action(self):
        tree = TaskTree(target="target.test")
        tree.add_action(action="Port scan", tool="execute_shell_command",
                        result_summary="22,80,443 open", command="nmap -sV target.test")
        assert len(tree.nodes) == 1
        assert tree.nodes[0].phase == Phase.RECON

    def test_auto_phase_detection(self):
        """Generic shell commands drive phase via command inference."""
        tree = TaskTree()
        tree.add_action(action="Scan", tool="execute_shell_command", command="nmap -sV t")
        assert tree.current_phase == Phase.RECON

        tree.add_action(action="Dir bust", tool="execute_shell_command",
                        command="gobuster dir -u http://t")
        assert tree.current_phase == Phase.ENUM

        tree.add_action(action="SQLi test", tool="execute_shell_command",
                        command="sqlmap -u http://t --batch")
        assert tree.current_phase == Phase.VULN

    def test_command_phase_inference(self):
        assert infer_phase_from_command("nmap -sV host") == Phase.RECON
        assert infer_phase_from_command("gobuster dir -u http://x") == Phase.ENUM
        assert infer_phase_from_command("nikto -h http://x") == Phase.VULN
        assert infer_phase_from_command("hydra -l admin -P w ssh://x") == Phase.EXPLOIT
        assert infer_phase_from_command("linpeas.sh") == Phase.POST_EXPLOIT
        assert infer_phase_from_command("echo hi") is None

    def test_tool_phase_mapping(self):
        assert TOOL_PHASE_MAP["search_exploits"] == Phase.VULN
        assert TOOL_PHASE_MAP["examine_exploit"] == Phase.VULN
        assert TOOL_PHASE_MAP["execute_sandboxed_script"] == Phase.EXPLOIT
        assert TOOL_PHASE_MAP["create_shell_session"] == Phase.EXPLOIT
    
    def test_get_progress(self):
        tree = TaskTree(target="target.test")
        tree.add_action("Port scan", "nmap_scan", "3 ports open")
        tree.add_action("Dir enum", "gobuster_dir", "5 dirs found")
        
        progress = tree.get_progress()
        assert "target.test" in progress
        assert "ACTIVE" in progress or "actions" in progress
        assert "Port scan" in progress or "nmap_scan" in progress
    
    def test_get_findings_summary(self):
        tree = TaskTree(target="target.test")
        tree.add_action("Scan", "nmap_scan", "Port 80, 443 open")
        tree.add_action("Dir bust", "gobuster_dir", "/admin, /login found")
        
        summary = tree.get_findings_summary()
        assert "target.test" in summary
        assert "Port 80" in summary or "80" in summary
    
    def test_context_for_agent(self):
        tree = TaskTree(target="target.test")
        tree.add_action("Initial scan", "nmap_scan", "80 open")
        
        ctx = tree.get_context_for_agent()
        assert "PENTEST PROGRESS" in ctx
        assert "target.test" in ctx
    
    def test_empty_context(self):
        tree = TaskTree()
        assert tree.get_context_for_agent() == ""
    
    def test_advance_phase(self):
        tree = TaskTree()
        tree.advance_phase(Phase.EXPLOIT)
        assert tree.current_phase == Phase.EXPLOIT
        assert tree.phase_completions[Phase.RECON] is True
    
    def test_to_dict(self):
        tree = TaskTree(target="target.test")
        tree.add_action("Scan", "nmap_scan", "Open ports")
        d = tree.to_dict()
        assert d["target"] == "target.test"
        assert len(d["nodes"]) == 1


class TestTaskGraph:
    """Tests for the Penetration Task Graph (DAG)."""

    def test_add_and_get_task(self):
        tree = TaskTree(target="t")
        t = tree.add_task("Port scan", phase=Phase.RECON)
        assert t.id == "t1"
        assert tree.get_task("t1").description == "Port scan"
        assert t.status == "pending"

    def test_ready_tasks_respects_deps(self):
        tree = TaskTree()
        a = tree.add_task("recon", phase=Phase.RECON)          # t1
        b = tree.add_task("enum", deps=[a.id])                  # t2 needs t1
        # Only the dependency-free task is ready initially.
        ready_ids = {t.id for t in tree.ready_tasks()}
        assert ready_ids == {a.id}
        # Completing t1 unlocks t2.
        tree.mark(a.id, "done")
        ready_ids = {t.id for t in tree.ready_tasks()}
        assert ready_ids == {b.id}

    def test_mark_running_sets_phase(self):
        tree = TaskTree()
        t = tree.add_task("exploit", phase=Phase.EXPLOIT)
        tree.mark(t.id, "running")
        assert tree.current_phase == Phase.EXPLOIT
        assert tree.get_task(t.id).status == "running"

    def test_mark_invalid_status_raises(self):
        tree = TaskTree()
        t = tree.add_task("x")
        with pytest.raises(ValueError):
            tree.mark(t.id, "bogus")

    def test_tasks_complete(self):
        tree = TaskTree()
        assert tree.tasks_complete() is False   # no tasks
        a = tree.add_task("a")
        b = tree.add_task("b")
        assert tree.tasks_complete() is False
        tree.mark(a.id, "done")
        tree.mark(b.id, "skipped")
        assert tree.tasks_complete() is True

    def test_blocked_task_never_ready_after_failed_dep(self):
        tree = TaskTree()
        a = tree.add_task("a")
        b = tree.add_task("b", deps=[a.id])
        tree.mark(a.id, "failed")
        assert b.id not in {t.id for t in tree.ready_tasks()}

    def test_to_dict_includes_tasks(self):
        tree = TaskTree(target="t")
        tree.add_task("scan", phase=Phase.RECON)
        d = tree.to_dict()
        assert len(d["tasks"]) == 1
        assert d["tasks"][0]["id"] == "t1"

    def test_context_includes_task_graph(self):
        tree = TaskTree(target="t")
        tree.add_task("Port scan the host")
        ctx = tree.get_context_for_agent()
        assert "Task graph" in ctx
        assert "Port scan the host" in ctx


class TestTaskNode:
    """Tests for individual task nodes."""
    
    def test_create_node(self):
        node = TaskNode("Scan ports", tool="nmap_scan", phase=Phase.RECON)
        assert node.action == "Scan ports"
        assert node.status == "pending"
    
    def test_to_dict(self):
        node = TaskNode("Test", tool="nmap_scan", phase=Phase.RECON, status="done")
        d = node.to_dict()
        assert d["action"] == "Test"
        assert d["phase"] == "reconnaissance"
        assert d["status"] == "done"
