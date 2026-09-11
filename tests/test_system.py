"""System Integration Test v2 — end-to-end CVA verification with all enhancements."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

console = Console()


def run_system_checks():
    """Run all system integration checks.

    This is a manual, service-dependent harness (MongoDB/Qdrant/Ollama/MCP),
    not a pytest unit test — hence the non-``test_`` name so pytest does not
    collect it. Run directly with ``python tests/test_system.py``.
    """
    console.print("\n[bold cyan]╔══ CVA System Integration Test ══╗[/bold cyan]\n")
    
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
        # Check the core tools actually exposed by the MCP servers today.
        core_tools = ["execute_shell_command", "read_local_file",
                      "execute_sandboxed_script", "search_exploits", "examine_exploit"]
        loaded_core = [t for t in core_tools if t in tool_names]
        console.print(f"  ✓ Core tools: {', '.join(loaded_core)} ({len(loaded_core)}/{len(core_tools)})")
        results["mcp_tools"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["mcp_tools"] = f"FAIL: {e}"
    
    # ── 4. Shell + Hash Identify ──
    console.print("\n[bold]TEST 4: Tool Execution[/bold]")
    try:
        shell_tool = next((t for t in tools if t.name == "execute_shell_command"), None)
        if shell_tool:
            result = str(shell_tool.invoke({"command": "echo CVA_enhanced"}))
            assert "CVA_enhanced" in result
            console.print(f"  ✓ Shell: {result.strip()[:60]}")

        exploit_tool = next((t for t in tools if t.name == "search_exploits"), None)
        if exploit_tool:
            console.print("  ✓ search_exploits tool available")
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
    
    # ── 6. Knowledge Base (FTS5) ──
    console.print("\n[bold]TEST 6: Knowledge Base (FTS5)[/bold]")
    try:
        from src.knowledge.fts_kb import FTS5KnowledgeBase
        from src.config import settings
        kb = FTS5KnowledgeBase(settings.kb_db_path)
        stats = kb.get_stats()
        console.print(f"  ✓ Status: {stats.get('status', 'unknown')}, Documents: {stats.get('documents', '?')}")
        results["knowledge"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["knowledge"] = f"FAIL: {e}"
    
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
    
    # ── 10. Engine ──
    console.print("\n[bold]TEST 10: PentestEngine[/bold]")
    try:
        from src.engine import PentestEngine
        from src.brain.llm_provider import get_llm
        eng = PentestEngine(llm=get_llm(), tools=tools, target="http://t")
        console.print(f"  ✓ Engine created with {len(tools)} tools")
        results["engine"] = "PASS"
    except Exception as e:
        console.print(f"  ✗ {e}")
        results["engine"] = f"FAIL: {e}"
    
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
    success = run_system_checks()
    sys.exit(0 if success else 1)
