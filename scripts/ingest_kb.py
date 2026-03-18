#!/usr/bin/env python3
"""CVA Knowledge Base Ingestion — clones repos, chunks markdown, embeds, upserts to Qdrant.

Usage:
    python scripts/ingest_kb.py                  # Full ingest (all sources)
    python scripts/ingest_kb.py --sources owasp  # Single source
    python scripts/ingest_kb.py --dry-run        # Show stats without upserting
"""

import os
import sys
import json
import re
import time
import hashlib
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    Filter, FieldCondition, MatchValue,
)

# ── Config ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "sources"
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("KB_COLLECTION", "cva_kb")
EMBED_DIM = 768  # nomic-embed-text dimension
CHUNK_SIZE = 500  # tokens (~words) per chunk
CHUNK_OVERLAP = 50
BATCH_SIZE = 32   # embeddings per API call

# ── Source definitions ──────────────────────────────────────────────────────

SOURCES = {
    "owasp": {
        "repo": "https://github.com/OWASP/CheatSheetSeries.git",
        "dir": "CheatSheetSeries",
        "glob": "cheatsheets/*.md",
        "label": "OWASP Cheat Sheets",
    },
    "payloads": {
        "repo": "https://github.com/swisskyrepo/PayloadsAllTheThings.git",
        "dir": "PayloadsAllTheThings",
        "glob": "**/README.md",
        "label": "PayloadsAllTheThings",
    },
    "hacktricks": {
        "repo": "https://github.com/HackTricks-wiki/hacktricks.git",
        "dir": "hacktricks",
        "glob": "**/*.md",
        "label": "HackTricks",
    },
    "gtfobins": {
        "repo": "https://github.com/GTFOBins/GTFOBins.github.io.git",
        "dir": "GTFOBins.github.io",
        "glob": "_gtfobins/*",
        "label": "GTFOBins",
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
    """Auto-detect VAPT phase from file path and content snippet."""
    haystack = f"{filepath} {content[:500]}".lower()
    best_phase = "general"
    best_score = 0
    for phase, pattern in _PHASE_PATTERNS:
        score = len(re.findall(pattern, haystack, re.IGNORECASE))
        if score > best_score:
            best_score = score
            best_phase = phase
    return best_phase


# ── Text chunking ───────────────────────────────────────────────────────────

def clean_markdown(text: str) -> str:
    """Strip images, HTML tags, excessive whitespace from markdown."""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)          # images
    text = re.sub(r'<[^>]+>', '', text)                   # HTML tags
    text = re.sub(r'\n{3,}', '\n\n', text)                # excessive newlines
    return text.strip()


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks by word count."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start = end - overlap
    return chunks


def extract_section_heading(text: str, position: int) -> str:
    """Find the nearest markdown heading before a position in text."""
    lines = text[:position].split('\n')
    for line in reversed(lines):
        if line.startswith('#'):
            return line.lstrip('#').strip()[:80]
    return ""


# ── Embedding via Ollama ────────────────────────────────────────────────────

def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts using Ollama API (sequential, since
    the /api/embed endpoint only supports one input at a time for
    some model versions)."""
    embeddings = []
    for text in texts:
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": text},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            emb = data.get("embeddings", [data.get("embedding", [])])
            if isinstance(emb[0], list):
                embeddings.append(emb[0])
            else:
                embeddings.append(emb)
        except Exception as e:
            print(f"  ⚠ Embedding failed: {e}")
            embeddings.append([0.0] * EMBED_DIM)
    return embeddings


# ── Qdrant operations ──────────────────────────────────────────────────────

def ensure_collection(client: QdrantClient):
    """Create collection if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"✓ Created Qdrant collection: {COLLECTION}")
    else:
        print(f"✓ Collection exists: {COLLECTION}")


def upsert_chunks(client: QdrantClient, chunks: List[Dict], vectors: List[List[float]]):
    """Upsert embedded chunks into Qdrant."""
    points = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        point_id = chunk["id"]
        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "source": chunk["source"],
                "file": chunk["file"],
                "section": chunk.get("section", ""),
                "phase": chunk["phase"],
                "text": chunk["text"],
            },
        ))

    # Upsert in batches of 100
    for i in range(0, len(points), 100):
        batch = points[i:i+100]
        client.upsert(collection_name=COLLECTION, points=batch)


# ── Source processing ──────────────────────────────────────────────────────

def _process_gtfobins(source_name: str, source_dir: Path, files: list) -> List[Dict]:
    """Convert GTFOBins YAML entries to text chunks."""
    print(f"  Found {len(files)} GTFOBins entries")
    chunks = []
    for f in files:
        try:
            raw = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        binary_name = f.name
        # Convert YAML to readable text
        lines = [f"# GTFOBins: {binary_name}\n"]
        lines.append(f"Binary: {binary_name}")
        lines.append("This binary can be used to break out of restricted environments or abuse sudo/SUID permissions.\n")

        # Extract function categories from YAML
        current_func = ""
        for line in raw.split("\n"):
            stripped = line.strip()
            if stripped.startswith("functions:"):
                continue
            if not line.startswith(" ") and stripped.endswith(":"):
                current_func = stripped[:-1]
                lines.append(f"\n## {current_func}")
            elif "code:" in stripped:
                pass  # Code follows on next lines
            elif stripped.startswith("- binary:"):
                pass
            elif stripped and not stripped.startswith("contexts:") and not stripped.startswith("sudo:") and not stripped.startswith("suid:"):
                lines.append(stripped)

        text = "\n".join(lines)
        if len(text.strip()) < 50:
            continue

        text_chunks = chunk_text(text)
        for i, chunk_val in enumerate(text_chunks):
            chunk_id = hashlib.md5(f"{source_name}:{binary_name}:{i}".encode()).hexdigest()
            chunk_id_int = int(chunk_id[:15], 16)
            chunks.append({
                "id": chunk_id_int,
                "source": source_name,
                "file": f"_gtfobins/{binary_name}",
                "section": binary_name,
                "phase": "post_exploitation",
                "text": chunk_val,
            })
    return chunks


def process_source(source_name: str, source_cfg: dict) -> List[Dict]:
    """Walk markdown files for a source, chunk them, and return chunk dicts."""
    source_dir = DATA_DIR / source_cfg["dir"]
    if not source_dir.exists():
        print(f"  ⚠ Source dir not found: {source_dir} — skipping")
        return []

    glob_pattern = source_cfg["glob"]
    all_files = list(source_dir.glob(glob_pattern))

    # For GTFOBins: files are YAML without extensions, only keep files (not dirs)
    if source_name == "gtfobins":
        all_files = [f for f in all_files if f.is_file() and '.' not in f.name]
        return _process_gtfobins(source_name, source_dir, all_files)

    md_files = all_files

    # For HackTricks, filter to pentest-relevant directories only
    if source_name == "hacktricks":
        relevant_dirs = [
            "network-services-pentesting", "pentesting-web", "linux-hardening",
            "windows-hardening", "generic-methodologies-and-resources",
            "mobile-pentesting", "cloud-security", "forensics",
            "cryptography", "reversing", "exploiting",
        ]
        md_files = [
            f for f in md_files
            if any(rd in str(f) for rd in relevant_dirs)
            and "SUMMARY" not in f.name
            and len(f.read_text(errors="ignore").strip()) > 200
        ]
        # Cap at 500 most relevant files to keep ingest reasonable
        md_files = md_files[:500]

    print(f"  Found {len(md_files)} markdown files")

    all_chunks = []
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

        text_chunks = chunk_text(cleaned)
        for i, chunk_text_val in enumerate(text_chunks):
            # Deterministic ID from source + file + chunk index
            chunk_id = hashlib.md5(
                f"{source_name}:{rel_path}:{i}".encode()
            ).hexdigest()
            # Convert to int for Qdrant (use first 15 hex digits as int)
            chunk_id_int = int(chunk_id[:15], 16)

            section = extract_section_heading(cleaned, cleaned.find(chunk_text_val[:50]))

            all_chunks.append({
                "id": chunk_id_int,
                "source": source_name,
                "file": rel_path,
                "section": section,
                "phase": phase,
                "text": chunk_text_val,
            })

    return all_chunks


# ── Clone/pull repos ──────────────────────────────────────────────────────

def clone_or_pull(source_name: str, source_cfg: dict):
    """Git clone (shallow) or pull if already exists."""
    source_dir = DATA_DIR / source_cfg["dir"]
    if source_dir.exists():
        print(f"  {source_name}: already cloned, pulling updates...")
        subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(source_dir), capture_output=True, timeout=120,
        )
    else:
        print(f"  {source_name}: cloning {source_cfg['repo']}...")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", source_cfg["repo"]],
            cwd=str(DATA_DIR), capture_output=True, timeout=300,
        )


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CVA KB Ingestion")
    parser.add_argument("--sources", nargs="*", default=list(SOURCES.keys()),
                        choices=list(SOURCES.keys()),
                        help="Sources to ingest (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only show stats, don't embed or upsert")
    parser.add_argument("--skip-clone", action="store_true",
                        help="Skip git clone/pull step")
    args = parser.parse_args()

    print("╔══ CVA Knowledge Base Ingestion ══╗")
    print(f"  Ollama:  {OLLAMA_URL}")
    print(f"  Model:   {EMBED_MODEL}")
    print(f"  Qdrant:  {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"  Sources: {', '.join(args.sources)}")
    print(f"  Dry run: {args.dry_run}")
    print()

    # 1. Clone repos
    if not args.skip_clone:
        print("[1/4] Cloning/updating repos...")
        for src in args.sources:
            clone_or_pull(src, SOURCES[src])
        print()

    # 2. Process & chunk
    print("[2/4] Processing markdown files...")
    all_chunks = []
    for src in args.sources:
        print(f"\n  [{SOURCES[src]['label']}]")
        chunks = process_source(src, SOURCES[src])
        all_chunks.extend(chunks)
        print(f"  → {len(chunks)} chunks")

    print(f"\n  Total: {len(all_chunks)} chunks across {len(args.sources)} sources")

    if args.dry_run:
        # Show phase distribution
        phase_counts = {}
        for c in all_chunks:
            phase_counts[c["phase"]] = phase_counts.get(c["phase"], 0) + 1
        print("\n  Phase distribution:")
        for phase, count in sorted(phase_counts.items(), key=lambda x: -x[1]):
            print(f"    {phase:25s} {count:5d}")
        print("\n✓ Dry run complete. Use without --dry-run to embed and upsert.")
        return

    # 3. Embed
    print(f"\n[3/4] Embedding {len(all_chunks)} chunks with {EMBED_MODEL}...")
    # Test embedding model availability
    try:
        test_resp = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": "test"},
            timeout=30,
        )
        test_resp.raise_for_status()
        actual_dim = len(test_resp.json().get("embeddings", [[]])[0])
        print(f"  ✓ {EMBED_MODEL} ready (dim={actual_dim})")
    except Exception as e:
        print(f"  ✗ Cannot reach embedding model: {e}")
        print(f"  Pull it first: curl {OLLAMA_URL}/api/pull -d '{{\"name\":\"{EMBED_MODEL}\"}}'")
        sys.exit(1)

    all_vectors = []
    start_time = time.time()
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i+BATCH_SIZE]
        texts = [c["text"][:2000] for c in batch]  # Cap at 2000 chars per chunk
        vectors = embed_batch(texts)
        all_vectors.extend(vectors)

        done = min(i + BATCH_SIZE, len(all_chunks))
        elapsed = time.time() - start_time
        rate = done / elapsed if elapsed > 0 else 0
        eta = (len(all_chunks) - done) / rate if rate > 0 else 0
        print(f"  {done}/{len(all_chunks)} ({rate:.1f}/s, ETA {eta:.0f}s)", end="\r")

    elapsed = time.time() - start_time
    print(f"\n  ✓ Embedded {len(all_vectors)} chunks in {elapsed:.1f}s")

    # 4. Upsert to Qdrant
    print(f"\n[4/4] Upserting to Qdrant ({QDRANT_HOST}:{QDRANT_PORT})...")
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        # Update EMBED_DIM to actual
        global EMBED_DIM
        EMBED_DIM = actual_dim
        ensure_collection(client)
        upsert_chunks(client, all_chunks, all_vectors)
        info = client.get_collection(COLLECTION)
        print(f"  ✓ Collection '{COLLECTION}': {info.points_count} points")
    except Exception as e:
        print(f"  ✗ Qdrant error: {e}")
        print("  Make sure Qdrant is running: docker run -p 6333:6333 qdrant/qdrant")
        sys.exit(1)

    print(f"\n╚══ Ingestion complete in {time.time() - start_time:.1f}s ══╝")


if __name__ == "__main__":
    main()
