"""CVA Auto Mode — fully autonomous VAPT with real-time streaming output.

Architecture (CAI-inspired):
    Single ReAct agent with ALL tools. The agent loops automatically:
    LLM → tool call → result → LLM → tool call → result → ...
    until it decides it's done.

    No per-phase specialist agents. One agent controls the whole engagement,
    just like CAI's one_tool_agent pattern. The system prompt gives it full
    VAPT methodology and it self-directs through all phases.

    Real-time streaming shows every thought, tool call, and result as they
    happen via stream_mode='messages'.
"""

import os
import sys
import re
import time
import json
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, Future

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.table import Table
from rich.markup import escape
from rich import box

from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, ToolMessage, BaseMessage,
)

from src.config import settings
from src.brain.thinking import parse_thinking, strip_thinking
from src.brain.llm_provider import get_llm
from src.reporting.generator import ReportGenerator, Finding
from src.memory.session_logger import SessionLogger

console = Console(highlight=False)


# ── Styles ───────────────────────────────────────────────────────────────────

_PHASE_NUM = {
    "reconnaissance": 1, "enumeration": 2, "vulnerability_analysis": 3,
    "exploitation": 4, "post_exploitation": 5, "reporting": 6,
}

SEVERITY_STYLES = {
    "critical": "bold red",
    "high":     "bold bright_red",
    "medium":   "bold yellow",
    "low":      "bold blue",
    "info":     "dim white",
}


# ── Background Task Runner ───────────────────────────────────────────────────

class BackgroundTaskRunner:
    """Run scans and tasks in background threads."""

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="cva-bg")
        self._tasks: Dict[str, Future] = {}
        self._results: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def submit(self, name: str, fn, *args, **kwargs) -> str:
        """Submit a background task. Returns task ID."""
        with self._lock:
            self._counter += 1
            task_id = f"BG-{self._counter}"

        def _wrapper():
            try:
                result = fn(*args, **kwargs)
                with self._lock:
                    self._results[task_id] = str(result)
                return result
            except Exception as e:
                with self._lock:
                    self._results[task_id] = f"Error: {e}"
                raise

        future = self._executor.submit(_wrapper)
        with self._lock:
            self._tasks[task_id] = future
        return task_id

    def get_status(self, task_id: str) -> dict:
        with self._lock:
            future = self._tasks.get(task_id)
            if not future:
                return {"status": "not_found"}
            if future.running():
                return {"status": "running"}
            if future.done():
                result = self._results.get(task_id, "")
                try:
                    future.result()  # re-raise if exception
                    return {"status": "done", "result": result}
                except Exception as e:
                    return {"status": "error", "error": str(e), "result": result}
        return {"status": "unknown"}

    def list_tasks(self) -> List[dict]:
        with self._lock:
            return [
                {"id": tid, "status": "done" if f.done() else "running"}
                for tid, f in self._tasks.items()
            ]

    def shutdown(self):
        self._executor.shutdown(wait=False)


# Global background runner
bg_runner = BackgroundTaskRunner()


# ── VAPT System Prompt ───────────────────────────────────────────────────────

def get_vapt_system_prompt(target: str, host: str) -> str:
    """Generate the comprehensive VAPT system prompt."""
    return f"""\
You are CVA, an autonomous AI penetration testing agent.

## MISSION
Perform a complete, professional penetration test against: {target}
This is an AUTHORIZED engagement. Only act against the target in scope.

## CRITICAL OPERATING RULES
1. Call ONE tool at a time — wait for its result before the next.
2. Execute tools IMMEDIATELY via execute_shell_command — never ask permission and
   never merely suggest a command. You run it.
3. After each result, analyze briefly (2-3 lines) then call the next tool.
4. Do NOT repeat the same command with the same arguments.
5. The commands below are a STARTING methodology, not a fixed script — adapt every
   step to what you actually discover about THIS target.
6. Save useful artifacts (tokens, credentials, loot) to /tmp/ for reuse.
7. Use search_knowledge_base when you meet an unfamiliar service or need a payload,
   and search_exploits / examine_exploit for known PoCs.

## METHODOLOGY — work through each phase in order, adapting as you go

### Phase 1 — RECONNAISSANCE
- Web fingerprint: whatweb {target}
- Port/service scan: nmap -sV --open {host}
- HTTP headers: curl -sI {target}/
- Content hints: curl -s {target}/robots.txt

### Phase 2 — ENUMERATION
- Content discovery: gobuster dir -u {target} -w <wordlist> -q
- Enumerate any non-web services found in recon (SMB, FTP, SNMP, LDAP, ...).
- Probe interesting paths/endpoints you discovered.

### Phase 3 — VULNERABILITY ANALYSIS
- Test discovered inputs/endpoints for common flaws: SQLi, XSS, IDOR/broken access
  control, auth bypass, path traversal, SSRF (use curl / sqlmap as appropriate).
- Research identified service+version against known CVEs (search_exploits).

### Phase 4 — EXPLOITATION
- Validate each CONFIRMED vulnerability with a controlled exploit.
- Capture concrete evidence (requests, responses, tokens, extracted data).

### Phase 5 — POST-EXPLOITATION
- With any access gained, assess impact: enumerate users/data, escalate where
  possible, and describe the business impact.

### Phase 6 — REPORTING
When exploitation is complete, say "GENERATING FINAL REPORT" and summarize every
vulnerability with severity (CRITICAL/HIGH/MEDIUM/LOW), evidence, and remediation.

## TARGET
- URL/target: {target}
- Host: {host}

Start with Phase 1. Call your FIRST tool NOW.
"""



# ── Auto Runner ──────────────────────────────────────────────────────────────

class AutoRunner:
    """Drives the fully autonomous VAPT pipeline.

    Architecture: Single create_react_agent with ALL tools.
    The agent self-directs through all VAPT phases. We stream every
    message (thinking, tool calls, results, analysis) in real time.
    """

    def __init__(self, target: str, tools: list, model_override: str = None,
                 orchestrator=None, report_gen=None, session_logger=None):
        self.target = target.rstrip("/")
        self.host = self._extract_host(target)
        self.tools = tools
        self.start_time = time.time()
        self.tool_call_count = 0
        self.findings: List[Finding] = []
        self._stop = False
        self.current_phase = "reconnaissance"

        # Use existing subsystems if provided (from /auto command)
        self.report_gen = report_gen or ReportGenerator()
        self.report_gen.target = self.target
        self.report_gen.tester = "CVA v3 Auto Mode"
        self.session_logger = session_logger or SessionLogger()

        # Configure settings for auto mode
        settings.require_approval = False

        if model_override:
            parts = model_override.split(":", 1)
            provider = parts[0]
            model = parts[1] if len(parts) > 1 else None
            settings.llm_provider = provider
            if model and provider == "ollama":
                settings.ollama_model = model
            elif model and provider == "openai":
                settings.openai_model = model

        # Build the shared planner/executor engine
        self._build_engine()

    def _extract_host(self, target: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(target)
        return parsed.hostname or target

    def _build_engine(self):
        """Build the shared PentestEngine (planner + per-task ReAct executor)."""
        from src.engine import PentestEngine

        self.llm = get_llm()
        self.engine = PentestEngine(
            llm=self.llm,
            tools=self.tools,
            target=self.target,
            session_logger=self.session_logger,
            on_event=self._on_engine_event,
        )

    # ── Engine event → Rich display bridge ─────────────────────────────────

    def _on_engine_event(self, kind: str, data: dict):
        """Render engine events with the existing Rich helpers."""
        if self._stop:
            return
        if kind == "planned":
            tasks = data.get("tasks", [])
            console.print(f"\n  [bold cyan]Planned {len(tasks)} tasks:[/bold cyan]")
            for t in tasks:
                console.print(f"    • [{t.phase.value}] {escape(t.description)}")
        elif kind == "task_start":
            task = data["task"]
            self._print_phase(task.phase.value.replace("_", " "),
                              _PHASE_NUM.get(task.phase.value, 1))
            console.print(f"  [bold white]▶ Task {task.id}: "
                          f"{escape(task.description)}[/bold white]")
        elif kind == "assistant":
            text = data.get("text", "")
            if not self._looks_like_hallucinated_calls(text):
                self._print_ai_response(text)
            self._detect_phase(text)
            self._extract_findings(text)
        elif kind == "tool_call":
            self._print_tool_call(data.get("name", ""), data.get("args", {}))
        elif kind == "tool_result":
            name, output = data.get("name", ""), data.get("output", "")
            self._print_tool_output(name, output)
            self._print_status_bar()
            self._extract_findings(output)
            self.report_gen.add_evidence(name, name, output[:2000])
        elif kind in ("task_error", "plan_error"):
            console.print(f"  [red]{kind}: {data.get('error', '')}[/red]")

    def _cap_output(self, raw) -> str:
        """Truncate tool output to avoid LLM context overflow."""
        MAX = 3000
        text = raw if isinstance(raw, str) else str(raw)
        if len(text) <= MAX:
            return text
        head = text[:MAX // 2]
        tail = text[-(MAX // 4):]
        omitted = len(text) - len(head) - len(tail)
        return f"{head}\n\n[... {omitted} chars omitted for brevity ...]\n\n{tail}"


    # ── Display Helpers ───────────────────────────────────────────────────

    def _print_banner(self):
        console.print()
        table = Table(show_header=False, box=box.DOUBLE, border_style="bold cyan",
                      width=70, padding=(0, 2))
        table.add_column(justify="center")
        table.add_row(Text("CVA — Cognitive VAPT Assistant v3", style="bold white"))
        table.add_row(Text("◆  AUTONOMOUS MODE  ◆", style="bold yellow"))
        table.add_row(Text(f"Target: {self.target}", style="bold cyan"))
        table.add_row(Text(f"Model:  {settings.llm_provider}:{getattr(settings, f'{settings.llm_provider}_model', settings.ollama_model)}", style="dim white"))
        table.add_row(Text(f"Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="dim white"))
        console.print(table, justify="center")
        console.print()

    def _print_phase(self, phase_name: str, phase_num: int):
        """Print phase transition banner."""
        styles = {
            "reconnaissance": "bold cyan", "enumeration": "bold blue",
            "vulnerability": "bold yellow", "exploitation": "bold red",
            "post-exploitation": "bold magenta", "reporting": "bold green",
        }
        style = styles.get(phase_name.lower(), "bold white")
        console.print()
        console.print(Rule(
            f"[{style}] PHASE {phase_num}: {phase_name.upper()} [{style}]",
            style=style
        ))
        console.print()
        self.current_phase = phase_name

    def _print_thinking(self, text: str):
        if not text.strip():
            return
        truncated = text[:2000]
        if len(text) > 2000:
            truncated += f"\n... [{len(text) - 2000} chars truncated]"
        panel = Panel(
            Text(truncated, style="dim italic white"),
            title="[dim yellow]💭 Thinking[/dim yellow]",
            border_style="dim yellow",
            padding=(0, 1),
        )
        console.print(panel)

    def _print_tool_call(self, tool_name: str, args: dict):
        self.tool_call_count += 1
        args_display = ""
        for k, v in args.items():
            v_str = str(v)
            if len(v_str) > 200:
                v_str = v_str[:200] + "..."
            args_display += f"  [dim white]{k}[/dim white]=[cyan]{escape(v_str)}[/cyan]\n"

        console.print(
            f"\n  [bold cyan]┌─ TOOL #{self.tool_call_count}: {tool_name} ──────────────────────[/bold cyan]"
        )
        if args_display:
            for line in args_display.strip().split("\n"):
                console.print(f"  [dim white]│[/dim white] {line}")

    def _print_tool_output(self, tool_name: str, output: str):
        lines = output.strip().split("\n")
        max_lines = 50
        display_lines = lines[:max_lines]

        console.print(f"  [bold cyan]└─ OUTPUT ({len(lines)} lines, {len(output)} bytes)[/bold cyan]")

        for line in display_lines:
            stripped = line.strip()
            if any(k in stripped.lower() for k in ["error", "fail", "denied"]):
                console.print(f"    [dim red]{escape(line)}[/dim red]")
            elif any(k in stripped.lower() for k in ["password", "token", "secret", "admin", "auth"]):
                console.print(f"    [bold yellow]{escape(line)}[/bold yellow]")
            elif any(k in stripped.lower() for k in ["open", "found", "success", "200", "vulner"]):
                console.print(f"    [bold green]{escape(line)}[/bold green]")
            else:
                console.print(f"    [white]{escape(line)}[/white]")

        if len(lines) > max_lines:
            console.print(f"    [dim white]... ({len(lines) - max_lines} more lines hidden)[/dim white]")
        console.print()

    def _print_ai_response(self, content: str):
        if not content.strip():
            return
        truncated = content[:4000]
        if len(content) > 4000:
            truncated += f"\n\n[{len(content) - 4000} more chars...]"
        panel = Panel(
            Text(truncated, style="white"),
            title="[bold green]🤖 CVA ANALYSIS[/bold green]",
            border_style="green",
            padding=(0, 1),
        )
        console.print(panel)

    def _print_status_bar(self):
        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        console.print(
            f"  [dim white]⏱ {mins:02d}:{secs:02d} │ "
            f"Phase: [bold]{self.current_phase.title()}[/bold] │ "
            f"Tools: {self.tool_call_count} │ "
            f"Findings: {len(self.findings)}[/dim white]"
        )

    def _print_finding(self, finding: Finding):
        sty = SEVERITY_STYLES.get(finding.severity, "white")
        console.print(f"\n  🔴 FINDING [{sty}][{finding.severity.upper()}][/{sty}]: "
                      f"[bold white]{escape(finding.title)}[/bold white]")

    # ── Phase detection from agent output ─────────────────────────────────

    def _detect_phase(self, text: str):
        """Detect phase transitions from the agent's output."""
        lower = text.lower()
        phase_signals = [
            (2, "enumeration", ["phase 2", "enumeration", "directory brute", "gobuster", "ffuf"]),
            (3, "vulnerability", ["phase 3", "vulnerability analysis", "vuln scan", "sql injection test", "xss test"]),
            (4, "exploitation", ["phase 4", "exploitation", "exploiting", "confirmed exploit"]),
            (5, "post-exploitation", ["phase 5", "post-exploitation", "post exploitation", "privilege escalation"]),
            (6, "reporting", ["phase 6", "generating final report", "report", "remediation"]),
        ]
        for num, name, keywords in phase_signals:
            if any(kw in lower for kw in keywords):
                if name != self.current_phase:
                    self._print_phase(name, num)
                break

    # ── Finding extraction from agent output ──────────────────────────────

    def _extract_findings(self, text: str):
        """Parse findings from the agent's analysis text."""
        lower = text.lower()

        finding_patterns = [
            # (keyword match, severity, title template)
            (["sql injection", "sqli", "authentication bypass"], "critical",
             "SQL Injection"),
            (["xss", "cross-site scripting", "script injection"], "high",
             "Cross-Site Scripting (XSS)"),
            (["sensitive file", "file exposure", "/ftp/", "directory listing"], "high",
             "Sensitive File Exposure"),
            (["broken access control", "idor", "unauthorized access", "unauthenticated"], "high",
             "Broken Access Control"),
            (["default credential", "admin123", "weak password"], "medium",
             "Default/Weak Credentials"),
            (["information disclosure", "stack trace", "verbose error", "debug info"], "low",
             "Information Disclosure"),
            (["jwt", "token", "forged token"], "high",
             "JWT/Token Vulnerability"),
            (["ssrf", "server-side request"], "high",
             "Server-Side Request Forgery"),
            (["directory traversal", "path traversal", "lfi", "local file inclusion"], "high",
             "Path Traversal / LFI"),
            (["rce", "remote code execution", "command injection"], "critical",
             "Remote Code Execution"),
        ]

        for keywords, severity, title in finding_patterns:
            # Only add if confirmed (vulnerable, success, confirmed, exploited)
            confirms = ["vulnerable", "success", "confirmed", "exploited",
                         "obtained", "bypass"]
            has_keyword = any(kw in lower for kw in keywords)
            has_confirm = any(cf in lower for cf in confirms)

            if has_keyword and has_confirm:
                # Don't add duplicate findings
                existing = {f.title for f in self.findings}
                if title not in existing:
                    # Try to extract evidence from nearby text
                    evidence = ""
                    for kw in keywords:
                        idx = lower.find(kw)
                        if idx >= 0:
                            start = max(0, idx - 100)
                            end = min(len(text), idx + 300)
                            evidence = text[start:end].strip()
                            break

                    finding = Finding(
                        title=title,
                        severity=severity,
                        description=f"Detected during autonomous VAPT of {self.target}",
                        evidence=evidence[:500],
                        remediation="See detailed report.",
                        tool="CVA-Auto",
                        category=title.split("(")[0].strip() if "(" in title else title,
                    )
                    self.findings.append(finding)
                    self.report_gen.add_finding(finding)
                    self._print_finding(finding)

    def _looks_like_hallucinated_calls(self, text: str) -> bool:
        """Detect if the LLM wrote tool call JSON as text instead of calling tools."""
        indicators = [
            '"name": "execute_shell_command"',
            '"name": "execute_sandboxed_script"',
            '{"name": "execute_',
            'function call',
            'function calls:',
        ]
        lower = text.lower()
        return any(ind.lower() in lower for ind in indicators)

    # ── Report Generation ─────────────────────────────────────────────────

    def _generate_report(self) -> str:
        """Generate the final report from discovered findings."""
        console.print()
        console.print(Rule("[bold green] PHASE 6: REPORTING [/bold green]", style="bold green"))
        console.print()

        if not self.findings:
            console.print("  [yellow]No findings were automatically extracted.[/yellow]")
            console.print("  [yellow]Generating report from agent conversation...[/yellow]")

        os.makedirs("reports", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Generate executive summary via the agent
        summary_prompt = f"""Based on all the testing you've performed against {self.target},
write a PROFESSIONAL EXECUTIVE SUMMARY for a penetration test report.

Include:
1. Overall security posture assessment (2-3 sentences for management)
2. Summary table of findings by severity (Critical/High/Medium/Low counts)
3. Top 3 immediate remediation priorities
4. Overall risk rating: CRITICAL / HIGH / MEDIUM / LOW

List EVERY vulnerability you confirmed with its severity, CVSS score, and one-line description.
Be concise, factual, and professional."""

        console.print("  [bold yellow]◆ Generating executive summary...[/bold yellow]\n")
        try:
            resp = self.llm.invoke([
                SystemMessage(content="You are a professional penetration test report writer."),
                HumanMessage(content=summary_prompt),
            ])
            exec_summary = getattr(resp, "content", "") or ""
        except Exception as e:
            exec_summary = f"(Executive summary generation failed: {e})"

        # Build report
        md_content = self.report_gen.generate_markdown()
        clean_summary = strip_thinking(exec_summary)
        md_content += f"\n\n## Executive Summary\n\n{clean_summary}"

        md_path = f"reports/auto_{ts}.md"
        html_path = f"reports/auto_{ts}.html"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        console.print(f"  [bold green]✓ Markdown report:[/bold green] [cyan]{md_path}[/cyan]")

        try:
            html_content = self.report_gen.generate_html()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            console.print(f"  [bold green]✓ HTML report:[/bold green] [cyan]{html_path}[/cyan]")
        except Exception as e:
            console.print(f"  [yellow]HTML report failed: {e}[/yellow]")
            html_path = None

        console.print(f"  [dim white]  Findings: {len(self.report_gen.findings)} | "
                      f"Evidence items: {len(self.report_gen.raw_evidence)}[/dim white]")

        return md_path

    # ── Main Entry Point ──────────────────────────────────────────────────

    def run(self) -> str:
        """Run the full autonomous VAPT pipeline."""
        self._print_banner()

        console.print(Rule("[bold cyan]INITIALISING[/bold cyan]", style="cyan"))
        console.print(f"  [cyan]Tools loaded:[/cyan] {len(self.tools)}")
        for t in self.tools:
            console.print(f"    • {t.name}")
        console.print(f"  [cyan]Guardrails:[/cyan] {'enabled' if settings.guardrails_enabled else 'disabled'}")
        console.print(f"  [cyan]Approval gate:[/cyan] DISABLED (auto mode)")
        console.print()

        # The engine plans the engagement into a task graph and executes each
        # task (planner → task graph → per-task ReAct executor). Display is
        # driven by _on_engine_event.
        goal = (f"Perform a complete, professional penetration test of "
                f"{self.target} and report all findings.")
        try:
            self.engine.run(goal)
        except KeyboardInterrupt:
            console.print("\n  [yellow]Interrupted by user — finishing...[/yellow]")
            self._stop = True

        # Generate report
        if not self._stop:
            report_path = self._generate_report()
        else:
            report_path = "reports/interrupted.md"

        # Final summary
        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)

        console.print()
        console.print(Rule("[bold green]VAPT COMPLETE[/bold green]", style="bold green"))
        console.print()

        summary = Table(show_header=True, box=box.ROUNDED, border_style="green",
                        title="[bold green]Engagement Summary[/bold green]")
        summary.add_column("Metric", style="bold white")
        summary.add_column("Value", style="cyan")
        summary.add_row("Target", self.target)
        summary.add_row("Duration", f"{mins}m {secs}s")
        summary.add_row("Tool Calls", str(self.tool_call_count))
        summary.add_row("Findings", str(len(self.findings)))
        summary.add_row("Critical", str(sum(1 for f in self.findings if f.severity == "critical")))
        summary.add_row("High", str(sum(1 for f in self.findings if f.severity == "high")))
        summary.add_row("Medium", str(sum(1 for f in self.findings if f.severity == "medium")))
        summary.add_row("Low", str(sum(1 for f in self.findings if f.severity == "low")))
        summary.add_row("Report", report_path)
        console.print(summary)
        console.print()

        return report_path


# ── Public Entry Points ──────────────────────────────────────────────────────

def run_auto(target: str, model: str = None):
    """Entry point for --auto CLI flag."""
    from src.tools.mcp_client import get_mcp_tools
    from src.tools.shell_session import get_session_tools, shutdown_all

    console.print(Rule("[cyan]Loading Tools[/cyan]", style="cyan"))

    tools = []
    try:
        mcp = get_mcp_tools()
        tools.extend(mcp)
        console.print(f"  ✓ MCP tools: {[t.name for t in mcp]}")
    except Exception as e:
        console.print(f"  [yellow]MCP tools failed: {e}[/yellow]")

    sess = get_session_tools()
    tools.extend(sess)
    console.print(f"  ✓ Session tools: {[t.name for t in sess]}")

    # Register the knowledge-base search tool (FTS5 lexical KB).
    try:
        from src.config import settings as _settings
        from src.knowledge.fts_kb import FTS5KnowledgeBase
        from src.knowledge.rag import KnowledgeService
        from src.tools.kb_tool import setup_kb_tool, search_knowledge_base
        setup_kb_tool(KnowledgeService([FTS5KnowledgeBase(_settings.kb_db_path)]))
        tools.append(search_knowledge_base)
        console.print("  ✓ KB tool: search_knowledge_base")
    except Exception as e:
        console.print(f"  [yellow]KB tool failed: {e}[/yellow]")

    if not tools:
        console.print("[red]Fatal: No tools loaded.[/red]")
        sys.exit(1)

    runner = AutoRunner(target=target, tools=tools, model_override=model)

    import atexit
    atexit.register(shutdown_all)

    try:
        report = runner.run()
        console.print(f"\n[bold green]✓ Report saved:[/bold green] [cyan]{report}[/cyan]\n")
    except KeyboardInterrupt:
        console.print("\n[yellow]Auto mode interrupted by user.[/yellow]")
        shutdown_all()


def run_auto_from_interactive(target: str, tools: list, orchestrator=None,
                               report_gen=None, session_logger=None):
    """Entry point for /auto slash command within interactive mode.

    Runs in the CURRENT thread (blocks the interactive loop until done).
    Uses the same tools already loaded by the interactive session.
    """
    runner = AutoRunner(
        target=target,
        tools=tools,
        report_gen=report_gen,
        session_logger=session_logger,
    )

    try:
        report = runner.run()
        return f"✓ Autonomous VAPT complete. Report: {report}"
    except KeyboardInterrupt:
        return "Auto mode interrupted by user."
    except Exception as e:
        return f"Auto mode error: {e}"
