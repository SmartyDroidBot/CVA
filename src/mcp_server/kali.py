"""Kali MCP Server — exposes pentesting tools via FastMCP."""

import subprocess
import shutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cva-kali-tools")


# ─── Reconnaissance Tools ────────────────────────────────────────────────────

@mcp.tool()
async def nmap_scan(target: str, options: str = "-sV -F") -> str:
    """Run an Nmap scan against a target. Returns scan output.
    
    Args:
        target: IP address, hostname, or CIDR range to scan
        options: Nmap command-line options (default: -sV -F for fast service detection)
    """
    nmap_path = shutil.which("nmap")
    if not nmap_path:
        return "Error: nmap not found. Install it with: sudo apt install nmap"
    
    cmd = f"{nmap_path} {options} {target}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        return output or "No output from nmap."
    except subprocess.TimeoutExpired:
        return "Error: Nmap scan timed out after 300 seconds."
    except Exception as e:
        return f"Error running nmap: {e}"


@mcp.tool()
async def gobuster_dir(url: str, wordlist: str = "/usr/share/wordlists/dirb/common.txt", options: str = "") -> str:
    """Run Gobuster directory enumeration against a web target.
    
    Args:
        url: Target URL (e.g., http://target.com)
        wordlist: Path to wordlist file
        options: Additional gobuster options
    """
    gobuster_path = shutil.which("gobuster")
    if not gobuster_path:
        return "Error: gobuster not found. Install it with: sudo apt install gobuster"
    
    cmd = f"{gobuster_path} dir -u {url} -w {wordlist} {options}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        output = result.stdout
        if result.stderr:
            # gobuster writes progress to stderr, filter it
            stderr_lines = [l for l in result.stderr.splitlines() if not l.startswith("Progress:")]
            if stderr_lines:
                output += "\n" + "\n".join(stderr_lines)
        return output or "No results found."
    except subprocess.TimeoutExpired:
        return "Error: Gobuster timed out after 300 seconds."
    except Exception as e:
        return f"Error running gobuster: {e}"


@mcp.tool()
async def nikto_scan(target: str, options: str = "") -> str:
    """Run Nikto web server vulnerability scanner.
    
    Args:
        target: Target URL or IP
        options: Additional nikto options
    """
    nikto_path = shutil.which("nikto")
    if not nikto_path:
        return "Error: nikto not found. Install it with: sudo apt install nikto"
    
    cmd = f"{nikto_path} -h {target} {options}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=600
        )
        return result.stdout or result.stderr or "No output from nikto."
    except subprocess.TimeoutExpired:
        return "Error: Nikto timed out after 600 seconds."
    except Exception as e:
        return f"Error running nikto: {e}"


# ─── Utility Tools ───────────────────────────────────────────────────────────

@mcp.tool()
async def execute_shell_command(command: str) -> str:
    """Execute a shell command on the local system. USE AS LAST RESORT.
    
    Only use this when no specific tool exists for the task.
    
    Args:
        command: The shell command to execute
    """
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def execute_sandboxed_script(script: str, language: str = "python") -> str:
    """Execute a script inside a Docker sandbox for safe execution.
    
    Args:
        script: The script content to execute
        language: Programming language (python or bash)
    """
    try:
        import docker
        client = docker.from_env()
        
        image = "python:3.12-slim" if language == "python" else "bash:latest"
        cmd = ["python", "-c", script] if language == "python" else ["bash", "-c", script]
        
        container = client.containers.run(
            image=image,
            command=cmd,
            detach=False,
            remove=True,
            network_mode="none",  # No network access for safety
            mem_limit="256m",
            cpu_period=100000,
            cpu_quota=50000,
            stdout=True,
            stderr=True,
        )
        return container.decode("utf-8") if isinstance(container, bytes) else str(container)
    except Exception as e:
        return f"Sandbox error: {e}"


# ─── Exploitation & Analysis Tools ────────────────────────────────────────────

@mcp.tool()
async def sqlmap_scan(url: str, options: str = "--batch --level=1 --risk=1") -> str:
    """Run SQLMap to test for SQL injection vulnerabilities.
    
    Args:
        url: Target URL with parameter (e.g., http://target.com/page?id=1)
        options: SQLMap options (default: --batch --level=1 --risk=1)
    """
    sqlmap_path = shutil.which("sqlmap")
    if not sqlmap_path:
        return "Error: sqlmap not found. Install it with: sudo apt install sqlmap"
    
    cmd = f"{sqlmap_path} -u '{url}' {options}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=600
        )
        output = result.stdout
        if result.stderr:
            err_lines = [l for l in result.stderr.splitlines() if "warning" not in l.lower()]
            if err_lines:
                output += "\n" + "\n".join(err_lines[-5:])
        return output or "No output from sqlmap."
    except subprocess.TimeoutExpired:
        return "Error: SQLMap timed out after 600 seconds."
    except Exception as e:
        return f"Error running sqlmap: {e}"


@mcp.tool()
async def hydra_bruteforce(target: str, service: str = "ssh",
                           username: str = "", userlist: str = "",
                           passlist: str = "/usr/share/wordlists/rockyou.txt",
                           options: str = "-t 4") -> str:
    """Run Hydra for password brute-forcing against a network service.
    
    Args:
        target: Target IP or hostname
        service: Service to attack (ssh, ftp, http-post-form, etc.)
        username: Single username to try (or leave empty to use userlist)
        userlist: Path to username wordlist
        passlist: Path to password wordlist (default: rockyou.txt)
        options: Additional hydra options (default: -t 4 for 4 threads)
    """
    hydra_path = shutil.which("hydra")
    if not hydra_path:
        return "Error: hydra not found. Install it with: sudo apt install hydra"
    
    user_flag = f"-l {username}" if username else f"-L {userlist}" if userlist else "-l admin"
    cmd = f"{hydra_path} {user_flag} -P {passlist} {options} {target} {service}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=600
        )
        return result.stdout or result.stderr or "No output from hydra."
    except subprocess.TimeoutExpired:
        return "Error: Hydra timed out after 600 seconds."
    except Exception as e:
        return f"Error running hydra: {e}"


@mcp.tool()
async def whatweb_scan(target: str, options: str = "-a 3") -> str:
    """Run WhatWeb to identify web technologies, CMS, frameworks, and server info.
    
    Args:
        target: Target URL or IP
        options: WhatWeb options (default: -a 3 for aggressive detection)
    """
    whatweb_path = shutil.which("whatweb")
    if not whatweb_path:
        return "Error: whatweb not found. Install it with: sudo apt install whatweb"
    
    cmd = f"{whatweb_path} {options} {target}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=120
        )
        return result.stdout or result.stderr or "No output from whatweb."
    except subprocess.TimeoutExpired:
        return "Error: WhatWeb timed out after 120 seconds."
    except Exception as e:
        return f"Error running whatweb: {e}"


@mcp.tool()
async def ffuf_fuzz(url: str, wordlist: str = "/usr/share/wordlists/dirb/common.txt",
                    options: str = "-mc 200,301,302,403") -> str:
    """Run FFuF (Fuzz Faster U Fool) for web fuzzing — directories, parameters, vhosts.
    
    Use FUZZ keyword in URL to mark the injection point.
    Example: http://target.com/FUZZ
    
    Args:
        url: Target URL with FUZZ keyword (e.g., http://target.com/FUZZ)
        wordlist: Path to wordlist
        options: FFuF options (default: filter for common status codes)
    """
    ffuf_path = shutil.which("ffuf")
    if not ffuf_path:
        return "Error: ffuf not found. Install it with: sudo apt install ffuf"
    
    cmd = f"{ffuf_path} -u {url} -w {wordlist} {options}"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        return result.stdout or result.stderr or "No output from ffuf."
    except subprocess.TimeoutExpired:
        return "Error: FFuF timed out after 300 seconds."
    except Exception as e:
        return f"Error running ffuf: {e}"


@mcp.tool()
async def curl_request(url: str, method: str = "GET",
                       headers: str = "", data: str = "",
                       options: str = "-s -i") -> str:
    """Make an HTTP request using curl — useful for API testing, header inspection, etc.
    
    Args:
        url: Target URL
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        headers: Custom headers as -H flags (e.g., -H 'Content-Type: application/json')
        data: Request body data for POST/PUT
        options: Additional curl options (default: -s -i for silent with headers)
    """
    cmd = f"curl -X {method} {options} {headers}"
    if data:
        cmd += f" -d '{data}'"
    cmd += f" '{url}'"
    
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]: {result.stderr}"
        return output or "(empty response)"
    except subprocess.TimeoutExpired:
        return "Error: curl request timed out after 30 seconds."
    except Exception as e:
        return f"Error running curl: {e}"


@mcp.tool()
async def hash_identify(hash_value: str) -> str:
    """Identify the type of a hash and attempt to crack common hashes.
    
    Args:
        hash_value: The hash string to identify
    """
    result_lines = [f"Hash: {hash_value}", f"Length: {len(hash_value)} chars", ""]
    
    # Simple hash type identification by length and charset
    h = hash_value.strip()
    candidates = []
    
    if len(h) == 32 and all(c in '0123456789abcdefABCDEF' for c in h):
        candidates.extend(["MD5", "NTLM"])
    elif len(h) == 40 and all(c in '0123456789abcdefABCDEF' for c in h):
        candidates.append("SHA-1")
    elif len(h) == 64 and all(c in '0123456789abcdefABCDEF' for c in h):
        candidates.append("SHA-256")
    elif len(h) == 128 and all(c in '0123456789abcdefABCDEF' for c in h):
        candidates.append("SHA-512")
    elif h.startswith("$2b$") or h.startswith("$2a$"):
        candidates.append("bcrypt")
    elif h.startswith("$6$"):
        candidates.append("SHA-512 (Unix crypt)")
    elif h.startswith("$5$"):
        candidates.append("SHA-256 (Unix crypt)")
    elif h.startswith("$1$"):
        candidates.append("MD5 (Unix crypt)")
    elif h.startswith("$apr1$"):
        candidates.append("Apache APR1-MD5")
    elif ":" in h and len(h.split(":")[0]) == 32:
        candidates.append("LM:NTLM (Windows hash pair)")
    elif len(h) == 13:
        candidates.append("DES (Unix crypt)")
    
    # Try hash-identifier if available
    hashid_path = shutil.which("hash-identifier") or shutil.which("hashid")
    if hashid_path:
        try:
            proc = subprocess.run(
                f"echo '{h}' | {hashid_path}", shell=True,
                capture_output=True, text=True, timeout=10
            )
            if proc.stdout.strip():
                result_lines.append("Tool analysis:")
                result_lines.append(proc.stdout[:500])
        except Exception:
            pass
    
    if candidates:
        result_lines.append(f"Likely hash types: {', '.join(candidates)}")
    else:
        result_lines.append("Unknown hash type. Try hashcat or john for identification.")
    
    result_lines.append(f"\nCracking suggestions:")
    result_lines.append(f"  hashcat -m <mode> '{h}' /usr/share/wordlists/rockyou.txt")
    result_lines.append(f"  john --wordlist=/usr/share/wordlists/rockyou.txt hash.txt")
    
    return "\n".join(result_lines)


# ─── Research Tools ───────────────────────────────────────────────────────────

@mcp.tool()
async def search_exploitdb(query: str) -> str:
    """Search ExploitDB for known exploits and vulnerabilities.
    
    Args:
        query: Search term (e.g., 'Apache 2.4.49', 'CVE-2021-44228')
    """
    searchsploit_path = shutil.which("searchsploit")
    if searchsploit_path:
        try:
            result = subprocess.run(
                f"{searchsploit_path} {query}", shell=True,
                capture_output=True, text=True, timeout=30
            )
            return result.stdout or "No results found."
        except Exception as e:
            return f"searchsploit error: {e}"
    
    # Fallback: web search
    try:
        import httpx
        url = f"https://www.exploit-db.com/search?q={query}"
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                        headers={"User-Agent": "CVA-VAPT-Assistant/2.0"})
        return f"ExploitDB search URL: {url}\nStatus: {resp.status_code}\n(Use searchsploit for better results: sudo apt install exploitdb)"
    except Exception as e:
        return f"ExploitDB lookup failed: {e}"


@mcp.tool()
async def search_web(query: str) -> str:
    """Search the web for security information, documentation, or general knowledge.
    
    Args:
        query: Search query string
    """
    try:
        import httpx
        # Use DuckDuckGo Lite as a simple search fallback
        resp = httpx.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query},
            timeout=15,
            headers={"User-Agent": "CVA-VAPT-Assistant/2.0"},
            follow_redirects=True,
        )
        # Extract text content (basic parsing)
        from html.parser import HTMLParser
        
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.texts = []
                self.in_result = False
            def handle_data(self, data):
                text = data.strip()
                if text and len(text) > 20:
                    self.texts.append(text)
        
        parser = TextExtractor()
        parser.feed(resp.text)
        results = "\n".join(parser.texts[:10])
        return f"Web search results for '{query}':\n{results}" if results else f"No results found for: {query}"
    except Exception as e:
        return f"Web search failed: {e}"


if __name__ == "__main__":
    mcp.run()
