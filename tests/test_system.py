"""System Integration Test v2 — end-to-end CVA verification with all enhancements."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

console = Console()


def test_system():
    """Run all system integration checks."""
    console.print("\n[bold cyan]╔══ CVA v2 System Integration Test ══╗[/bold cyan]\n")
    
    results = {}
    tools = []
    
    # ── 1. Config ──
    console.print("[bold]TEST 1: Configuration[/bold]")
    try:
        from src.config import settings
        console.print(f"  ✓ Provider: {settings.llm_provider}, Model: {settings.ollama_model}")
        results["config"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["config"] = f"FAIL: {e}"
    
    # ── 2. Brain ──
    console.print("\n[bold]TEST 2: Brain (LLM + Thinking)[/bold]")
    try:
        from src.brain.llm_provider import get_llm
        from src.brain.thinking import parse_thinking
        llm = get_llm("ollama")
        r = parse_thinking("<think>reasoning</think>content")
        assert r.thinking == "reasoning" and r.content == "content"
        console.print(f"  ✓ LLM: {type(llm).__name__}, Thinking parser: OK")
        results["brain"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["brain"] = f"FAIL: {e}"
    
    # ── 3. MCP Tools ──
    console.print("\n[bold]TEST 3: MCP Tools[/bold]")
    try:
        from src.tools.mcp_client import get_mcp_tools
        tools = get_mcp_tools()
        tool_names = [t.name for t in tools]
        console.print(f"  ✓ {len(tools)} tools: {', '.join(tool_names)}")
        # Check new tools
        new_tools = ["sqlmap_scan", "hydra_bruteforce", "whatweb_scan", "ffuf_fuzz", "curl_request", "hash_identify"]
        loaded_new = [t for t in new_tools if t in tool_names]
        console.print(f"  ✓ New tools: {', '.join(loaded_new)} ({len(loaded_new)}/{len(new_tools)})")
        results["mcp_tools"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["mcp_tools"] = f"FAIL: {e}"
    
    # ── 4. Shell + Hash Identify ──
    console.print("\n[bold]TEST 4: Tool Execution[/bold]")
    try:
        shell_tool = next((t for t in tools if t.name == "execute_shell_command"), None)
        if shell_tool:
            result = shell_tool.run({"command": "echo 'CVA v2 enhanced'"})
            assert "CVA v2 enhanced" in result
            console.print(f"  ✓ Shell: {result.strip()}")
        
        hash_tool = next((t for t in tools if t.name == "hash_identify"), None)
        if hash_tool:
            result = hash_tool.run({"hash_value": "5d41402abc4b2a76b9719d911017c592"})
            assert "MD5" in result
            console.print(f"  ✓ Hash identify: MD5 detected")
        results["tools_exec"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["tools_exec"] = f"FAIL: {e}"
    
    # ── 5. MongoDB ──
    console.print("\n[bold]TEST 5: MongoDB Session Store[/bold]")
    try:
        from src.memory.session_store import SessionStore
        store = SessionStore()
        sid = store.create_session("sytest_v2")
        store.save_note(sid, "test", "integration test v2")
        store.save_finding(sid, {"type": "test", "port": 80, "severity": "info"})
        findings = store.get_findings(sid)
        assert len(findings) == 1
        store.delete_session(sid)
        store.close()
        console.print("  ✓ CRUD + findings + notes")
        results["mongodb"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["mongodb"] = f"FAIL: {e}"
    
    # ── 6. Qdrant ──
    console.print("\n[bold]TEST 6: Qdrant Vector KB[/bold]")
    try:
        from src.knowledge.vector_kb import VectorKB
        kb = VectorKB()
        stats = kb.get_stats()
        console.print(f"  ✓ Status: {stats.get('status', 'unknown')}, Points: {stats.get('points', '?')}")
        results["qdrant"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["qdrant"] = f"FAIL: {e}"
    
    # ── 7. Report Generator ──
    console.print("\n[bold]TEST 7: Report Generator[/bold]")
    try:
        from src.reporting.generator import ReportGenerator, Finding
        gen = ReportGenerator()
        gen.target = "10.0.0.1"
        gen.add_finding(Finding("Open SSH", severity="low", tool="nmap"))
        gen.add_finding(Finding("SQLi", severity="critical", cve="CVE-2024-9999"))
        md = gen.generate_markdown()
        html = gen.generate_html()
        assert "SQLi" in md and "CRITICAL" in md
        assert "SQLi" in html and "<!DOCTYPE html>" in html
        saved = gen.save(output_dir="/tmp/cva_systest", fmt="both")
        console.print(f"  ✓ Markdown: {len(md)} chars, HTML: {len(html)} chars")
        console.print(f"  ✓ Saved: {', '.join(os.path.basename(p) for p in saved)}")
        # Cleanup
        import shutil
        shutil.rmtree("/tmp/cva_systest", ignore_errors=True)
        results["reporting"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["reporting"] = f"FAIL: {e}"
    
    # ── 8. Task Tree ──
    console.print("\n[bold]TEST 8: Task Tree / Progress Tracker[/bold]")
    try:
        from src.tracker.task_tree import TaskTree, Phase
        tree = TaskTree(target="10.0.0.1")
        tree.add_action("Port scan", "nmap_scan", "22, 80, 443 open")
        tree.add_action("Dir enum", "gobuster_dir", "/admin, /login found")
        tree.add_action("SQLi test", "sqlmap_scan", "Vulnerable param: id")
        
        progress = tree.get_progress()
        assert "10.0.0.1" in progress
        assert tree.current_phase == Phase.EXPLOIT
        context = tree.get_context_for_agent()
        assert "PENTEST PROGRESS" in context
        console.print(f"  ✓ {len(tree.nodes)} actions tracked, phase: {tree.current_phase.value}")
        results["tracker"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["tracker"] = f"FAIL: {e}"
    
    # ── 9. Enhanced Commands ──
    console.print("\n[bold]TEST 9: Slash Commands[/bold]")
    try:
        from src.ui.commands import CommandHandler
        cmd = CommandHandler(task_tree=TaskTree(target="test"), report_gen=ReportGenerator())
        
        h_out, _ = cmd.execute("/help")
        assert "/report" in h_out and "/progress" in h_out
        
        t_out, _ = cmd.execute("/target 192.168.1.1")
        assert "192.168.1.1" in t_out
        
        p_out, _ = cmd.execute("/progress")
        assert "192.168.1.1" in p_out
        
        s_out, _ = cmd.execute("/settings")
        assert "Target" in s_out or "target" in s_out
        
        console.print("  ✓ /help, /target, /progress, /settings all work")
        results["commands"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["commands"] = f"FAIL: {e}"
    
    # ── 10. Orchestrator ──
    console.print("\n[bold]TEST 10: Orchestrator (Agent)[/bold]")
    try:
        from src.orchestrator import Orchestrator
        orch = Orchestrator(tools=tools)
        console.print(f"  ✓ Agent created with {len(tools)} tools")
        results["orchestrator"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["orchestrator"] = f"FAIL: {e}"
    
    # ── Summary ──
    console.print("\n[bold cyan]╔══ Results Summary ══╗[/bold cyan]")
    passed = sum(1 for v in results.values() if v == "PASS")
    total = len(results)
    for name, status in results.items():
        icon = "✓" if status == "PASS" else "✗"
        color = "green" if status == "PASS" else "red"
        console.print(f"  [{color}]{icon} {name:20s} {status}[/{color}]")
    
    console.print(f"\n  [bold]{passed}/{total} passed[/bold]")
    console.print("[bold cyan]╚═════════════════════╝[/bold cyan]\n")
    
    return passed == total


if __name__ == "__main__":
    success = test_system()
    sys.exit(0 if success else 1)
