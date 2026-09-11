"""Tests for Task Tree / Progress Tracker module."""

import pytest
from src.tracker.task_tree import (
    TaskTree, Phase, TaskNode, TOOL_PHASE_MAP, infer_phase_from_command,
)


class TestTaskTree:
    """Tests for VAPT progress tracking."""
    
    def test_create_tree(self):
        tree = TaskTree(target="192.168.1.1")
        assert tree.target == "192.168.1.1"
        assert tree.current_phase == Phase.RECON
        assert len(tree.nodes) == 0
    
    def test_add_action(self):
        tree = TaskTree(target="10.0.0.1")
        tree.add_action(action="Port scan", tool="execute_shell_command",
                        result_summary="22,80,443 open", command="nmap -sV 10.0.0.1")
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
        tree = TaskTree(target="10.0.0.1")
        tree.add_action("Port scan", "nmap_scan", "3 ports open")
        tree.add_action("Dir enum", "gobuster_dir", "5 dirs found")
        
        progress = tree.get_progress()
        assert "10.0.0.1" in progress
        assert "ACTIVE" in progress or "actions" in progress
        assert "Port scan" in progress or "nmap_scan" in progress
    
    def test_get_findings_summary(self):
        tree = TaskTree(target="example.com")
        tree.add_action("Scan", "nmap_scan", "Port 80, 443 open")
        tree.add_action("Dir bust", "gobuster_dir", "/admin, /login found")
        
        summary = tree.get_findings_summary()
        assert "example.com" in summary
        assert "Port 80" in summary or "80" in summary
    
    def test_context_for_agent(self):
        tree = TaskTree(target="test.com")
        tree.add_action("Initial scan", "nmap_scan", "80 open")
        
        ctx = tree.get_context_for_agent()
        assert "PENTEST PROGRESS" in ctx
        assert "test.com" in ctx
    
    def test_empty_context(self):
        tree = TaskTree()
        assert tree.get_context_for_agent() == ""
    
    def test_advance_phase(self):
        tree = TaskTree()
        tree.advance_phase(Phase.EXPLOIT)
        assert tree.current_phase == Phase.EXPLOIT
        assert tree.phase_completions[Phase.RECON] is True
    
    def test_to_dict(self):
        tree = TaskTree(target="10.0.0.1")
        tree.add_action("Scan", "nmap_scan", "Open ports")
        d = tree.to_dict()
        assert d["target"] == "10.0.0.1"
        assert len(d["nodes"]) == 1


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
