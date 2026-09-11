#!/usr/bin/env python3
"""CVA Knowledge Base Ingestion — clones repos, chunks markdown, builds an FTS5 index.

No embedding model, no vector DB: the index is a single SQLite FTS5 file
(``data/kb/cva_kb.sqlite3`` by default) queried by ``src/knowledge/fts_kb.py``.

Usage:
    python scripts/ingest_kb.py                 # clone/pull + build all sources
    python scripts/ingest_kb.py --rebuild       # rebuild index (same as default)
    python scripts/ingest_kb.py --skip-clone    # use the corpus already on disk
    python scripts/ingest_kb.py --sources owasp # a single source
    python scripts/ingest_kb.py --dry-run       # stats only, no index written
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

# Make ``src`` importable when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.fts_kb import build_index  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data" / "sources"
DEFAULT_DB = os.getenv("KB_DB_PATH", str(PROJECT_ROOT / "data" / "kb" / "cva_kb.sqlite3"))
CHUNK_SIZE = 500   # words per chunk
CHUNK_OVERLAP = 50

# ── Source definitions ──────────────────────────────────────────────────────

SOURCES = {
    "owasp": {
        "repo": "https://github.com/OWASP/CheatSheetSeries.git",
        "dir": "CheatSheetSeries", "glob": "cheatsheets/*.md",
        "label": "OWASP Cheat Sheets",
    },
    "payloads": {
        "repo": "https://github.com/swisskyrepo/PayloadsAllTheThings.git",
        "dir": "PayloadsAllTheThings", "glob": "**/README.md",
        "label": "PayloadsAllTheThings",
    },
    "hacktricks": {
        "repo": "https://github.com/HackTricks-wiki/hacktricks.git",
        "dir": "hacktricks", "glob": "**/*.md", "label": "HackTricks",
    },
    "gtfobins": {
        "repo": "https://github.com/GTFOBins/GTFOBins.github.io.git",
        "dir": "GTFOBins.github.io", "glob": "_gtfobins/*", "label": "GTFOBins",
    },
}

# ── Phase auto-tagger ───────────────────────────────────────────────────────

_PHASE_PATTERNS = [
    ("reconnaissance", r"recon|osint|dns|subdomain|whois|shodan|theharv|amass|subfinder|footprint"),
    ("enumeration", r"enum|directory|gobuster|ffuf|dirsearch|smb|nfs|snmp|ldap|nikto|brute.?dir"),
    ("vulnerability_analysis", r"xss|sqli|injection|vuln|csrf|ssrf|idor|lfi|rfi|xxe|deseriali|owasp"),
    ("exploitation", r"exploit|reverse.?shell|payload|metasploit|msfvenom|hydra|sqlmap|shell|upload|bypass"),
    ("post_exploitation", r"priv.?esc|post.?exploit|lateral|mimikatz|linpeas|winpeas|persistence|pivot|suid|sudo|gtfobins|lolbas"),
    ("reporting", r"report|evidence|documentation|cvss|remediat"),
]


def detect_phase(filepath: str, content: str = "") -> str:
    haystack = f"{filepath} {content[:500]}".lower()
    best_phase, best_score = "general", 0
    for phase, pattern in _PHASE_PATTERNS:
        score = len(re.findall(pattern, haystack, re.IGNORECASE))
        if score > best_score:
            best_score, best_phase = score, phase
    return best_phase


# ── Text processing ─────────────────────────────────────────────────────────

def clean_markdown(text: str) -> str:
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)   # images
    text = re.sub(r'<[^>]+>', '', text)            # HTML tags
    text = re.sub(r'\n{3,}', '\n\n', text)         # excess newlines
    return text.strip()


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    if len(words) <= chunk_size:
        return [text] if text.strip() else []
    chunks, start = [], 0
    while start < len(words):
        chunk = " ".join(words[start:start + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def extract_section_heading(text: str, position: int) -> str:
    for line in reversed(text[:position].split('\n')):
        if line.startswith('#'):
            return line.lstrip('#').strip()[:80]
    return ""


# ── Source processing ──────────────────────────────────────────────────────

def _process_gtfobins(source_name: str, files: list) -> List[Dict]:
    print(f"  Found {len(files)} GTFOBins entries")
    chunks = []
    for f in files:
        try:
            raw = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        binary_name = f.name
        lines = [f"# GTFOBins: {binary_name}\n", f"Binary: {binary_name}",
                 "This binary can be abused to break out of restricted "
                 "environments or abuse sudo/SUID permissions.\n"]
        for line in raw.split("\n"):
            stripped = line.strip()
            if stripped.startswith("functions:"):
                continue
            if not line.startswith(" ") and stripped.endswith(":"):
                lines.append(f"\n## {stripped[:-1]}")
            elif stripped and not stripped.startswith(("contexts:", "sudo:", "suid:", "- binary:")):
                lines.append(stripped)
        text = "\n".join(lines)
        if len(text.strip()) < 50:
            continue
        for chunk_val in chunk_text(text):
            chunks.append({
                "source": source_name, "section": binary_name,
                "phase": "post_exploitation", "text": chunk_val,
            })
    return chunks


def process_source(source_name: str, cfg: dict) -> List[Dict]:
    source_dir = DATA_DIR / cfg["dir"]
    if not source_dir.exists():
        print(f"  ⚠ Source dir not found: {source_dir} — skipping")
        return []

    all_files = list(source_dir.glob(cfg["glob"]))

    if source_name == "gtfobins":
        entries = [f for f in all_files if f.is_file() and '.' not in f.name]
        return _process_gtfobins(source_name, entries)

    md_files = all_files
    if source_name == "hacktricks":
        relevant = [
            "network-services-pentesting", "pentesting-web", "linux-hardening",
            "windows-hardening", "generic-methodologies-and-resources",
            "mobile-pentesting", "cloud-security", "forensics",
            "cryptography", "reversing", "exploiting",
        ]
        md_files = [
            f for f in md_files
            if any(rd in str(f) for rd in relevant)
            and "SUMMARY" not in f.name
            and len(f.read_text(errors="ignore").strip()) > 200
        ][:500]

    print(f"  Found {len(md_files)} markdown files")

    chunks = []
    for md_file in md_files:
        try:
            raw = md_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if len(raw.strip()) < 100:
            continue
        cleaned = clean_markdown(raw)
        rel_path = str(md_file.relative_to(source_dir))
        phase = detect_phase(rel_path, cleaned)
        for chunk_val in chunk_text(cleaned):
            section = extract_section_heading(cleaned, cleaned.find(chunk_val[:50]))
            chunks.append({
                "source": source_name, "section": section,
                "phase": phase, "text": chunk_val,
            })
    return chunks


def clone_or_pull(source_name: str, cfg: dict):
    source_dir = DATA_DIR / cfg["dir"]
    if source_dir.exists():
        print(f"  {source_name}: already cloned, pulling updates...")
        subprocess.run(["git", "pull", "--ff-only"], cwd=str(source_dir),
                       capture_output=True, timeout=120)
    else:
        print(f"  {source_name}: cloning {cfg['repo']}...")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", cfg["repo"]],
                       cwd=str(DATA_DIR), capture_output=True, timeout=300)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CVA KB Ingestion (FTS5)")
    parser.add_argument("--sources", nargs="*", default=list(SOURCES.keys()),
                        choices=list(SOURCES.keys()), help="Sources (default: all)")
    parser.add_argument("--db", default=DEFAULT_DB, help="Output SQLite FTS5 path")
    parser.add_argument("--dry-run", action="store_true", help="Stats only")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild the index (default behaviour)")
    parser.add_argument("--skip-clone", action="store_true",
                        help="Use the corpus already on disk")
    args = parser.parse_args()

    print("╔══ CVA Knowledge Base Ingestion (FTS5) ══╗")
    print(f"  Output:  {args.db}")
    print(f"  Sources: {', '.join(args.sources)}\n")

    if not args.skip_clone:
        print("[1/3] Cloning/updating repos...")
        for src in args.sources:
            clone_or_pull(src, SOURCES[src])
        print()

    print("[2/3] Processing markdown files...")
    all_chunks: List[Dict] = []
    for src in args.sources:
        print(f"\n  [{SOURCES[src]['label']}]")
        chunks = process_source(src, SOURCES[src])
        all_chunks.extend(chunks)
        print(f"  → {len(chunks)} chunks")

    print(f"\n  Total: {len(all_chunks)} chunks")

    phase_counts: Dict[str, int] = {}
    for c in all_chunks:
        phase_counts[c["phase"]] = phase_counts.get(c["phase"], 0) + 1
    print("\n  Phase distribution:")
    for phase, count in sorted(phase_counts.items(), key=lambda x: -x[1]):
        print(f"    {phase:25s} {count:5d}")

    if args.dry_run:
        print("\n✓ Dry run complete. Re-run without --dry-run to build the index.")
        return

    print(f"\n[3/3] Building FTS5 index at {args.db}...")
    n = build_index(args.db, all_chunks)
    print(f"  ✓ Indexed {n} chunks")
    print("\n╚══ Ingestion complete ══╝")


if __name__ == "__main__":
    main()
