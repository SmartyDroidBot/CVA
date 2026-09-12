#!/usr/bin/env bash
#
# CVA one-command demo — model-agnostic, bring-your-own-target.
#
# CVA never picks an LLM for you and ships no target. You:
#   - choose your provider and default model in .env (the config file), and
#   - stand up (and are authorized to test) your own target, then pass its URL.
#
# This script then: verifies the configured provider, ensures the FTS5 knowledge
# base exists, runs an autonomous engagement against your target, and hands you
# the generated report.
#
# Usage:  ./demo.sh <target-url>

set -euo pipefail
cd "$(dirname "$0")"

KB_DB="data/kb/cva_kb.sqlite3"

info() { printf '\033[1;36m[demo]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[demo]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[demo] %s\033[0m\n' "$*" >&2; exit 1; }

env_get() { grep -E "^${1}=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r'; }

TARGET="${1:-}"
[[ -n "$TARGET" ]] || die "Usage: ./demo.sh <target-url>
      Stand up your own authorized target first, then pass its URL. CVA does not
      ship or assume any target."

command -v uv >/dev/null || die "uv is not installed — see https://astral.sh/uv"

# ── 1. Config file (you choose the model here) ──────────────────────────────────
if [[ ! -f .env ]]; then
    cp .env.example .env
    die "Created .env — open it, set LLM_PROVIDER and the model (and an API key
      for a cloud provider), then re-run. CVA is model-agnostic and will not
      choose a provider for you."
fi

PROVIDER="$(env_get LLM_PROVIDER)"; PROVIDER="${PROVIDER:-ollama}"
info "LLM provider (from .env): ${PROVIDER}"

# ── 2. Verify the configured provider is ready ──────────────────────────────────
case "$PROVIDER" in
    ollama)
        BASE="$(env_get OLLAMA_BASE_URL)"; BASE="${BASE:-http://localhost:11434}"
        MODEL="$(env_get OLLAMA_MODEL)"; MODEL="${MODEL:-qwen3:8b}"
        curl -sf "${BASE}/api/tags" >/dev/null \
            || die "Ollama not reachable at ${BASE}. Start it (ollama serve) or set a cloud provider in .env."
        curl -sf "${BASE}/api/tags" | grep -q "\"${MODEL%%:*}" \
            || die "Ollama model '${MODEL}' not found. Pull it first: ollama pull ${MODEL}"
        info "Ollama ready (${MODEL})"
        ;;
    openai|anthropic|google)
        KEYVAR="$(echo "$PROVIDER" | tr '[:lower:]' '[:upper:]')_API_KEY"
        KEYVAL="$(env_get "$KEYVAR")"; KEYVAL="${KEYVAL:-${!KEYVAR:-}}"
        [[ -n "$KEYVAL" ]] || die "${KEYVAR} is not set. Add it to .env to use the ${PROVIDER} provider."
        info "${PROVIDER} API key present"
        ;;
    *)
        die "Unknown LLM_PROVIDER='${PROVIDER}' in .env (use: ollama | openai | anthropic | google)"
        ;;
esac

# ── 3. Optional: MongoDB for session persistence (skipped if docker absent) ─────
if command -v docker >/dev/null; then
    info "Starting MongoDB (session persistence) ..."
    docker compose up -d >/dev/null 2>&1 || warn "Could not start MongoDB — continuing without persistence."
else
    warn "docker not found — running without MongoDB session persistence."
fi

# ── 4. Knowledge base ───────────────────────────────────────────────────────────
if [[ ! -f "$KB_DB" ]]; then
    info "Building the FTS5 knowledge base (one-time; clones sources if needed) ..."
    if compgen -G "data/sources/*/" >/dev/null 2>&1; then
        uv run python scripts/ingest_kb.py --skip-clone
    else
        uv run python scripts/ingest_kb.py
    fi
else
    info "Knowledge base present ($KB_DB)"
fi

# ── 5. Autonomous engagement against your target ────────────────────────────────
info "Running autonomous engagement against ${TARGET} ..."
uv run python cva.py --auto "${TARGET}"

LATEST="$(ls -t reports/*.md reports/*.html 2>/dev/null | head -1 || true)"
if [[ -n "$LATEST" ]]; then
    info "Done. Report: ${LATEST}"
else
    warn "Done, but no report file was found in reports/."
fi
