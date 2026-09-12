#!/usr/bin/env python3
"""CVA — Cognitive VAPT Assistant v3

Usage:
    # Interactive (copilot) mode (default):
    python cva.py

    # Autonomous mode — full VAPT against an authorized target you provide:
    python cva.py --auto <target-url>
    python cva.py --auto <target-url> --model openai:gpt-4o

    # Switch model (overrides .env for this run):
    python cva.py --model ollama:llama3.1
"""

import sys
import argparse
import os

# Ensure project root is in path regardless of how script is called
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def parse_args():
    parser = argparse.ArgumentParser(
        prog="cva",
        description="CVA — Cognitive VAPT Assistant v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cva.py                                  # Interactive (copilot) mode
  python cva.py --auto <target-url>              # Autonomous full VAPT
  python cva.py --auto <target-url> --model ollama:llama3.1
  python cva.py --model openai:gpt-4o            # Interactive with OpenAI
        """,
    )

    parser.add_argument(
        "--auto",
        metavar="TARGET",
        help="Autonomous mode: run full VAPT against the authorized TARGET you provide",
    )
    parser.add_argument(
        "--model",
        metavar="PROVIDER:MODEL",
        help="LLM to use (e.g. ollama:qwen3:8b, openai:gpt-4o, anthropic:claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--no-guardrails",
        action="store_true",
        help="Disable input guardrails (not recommended)",
    )
    parser.add_argument(
        "--no-approval",
        action="store_true",
        help="Disable the tool approval gate",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (verbose output)",
    )
    return parser.parse_args()


def apply_args(args):
    """Apply CLI args to settings before anything is initialised."""
    from src.config import settings

    if args.model:
        parts = args.model.split(":", 1)
        settings.llm_provider = parts[0]
        model = parts[1] if len(parts) > 1 else None
        if model:
            if parts[0] == "ollama":
                settings.ollama_model = model
            elif parts[0] == "openai":
                settings.openai_model = model
            elif parts[0] == "anthropic":
                settings.anthropic_model = model
            elif parts[0] == "google":
                settings.google_model = model

    if args.no_guardrails:
        settings.guardrails_enabled = False

    if args.no_approval:
        settings.require_approval = False

    if args.debug:
        settings.debug_mode = True


def main():
    args = parse_args()
    apply_args(args)

    if args.auto:
        # ── AUTONOMOUS MODE ───────────────────────────────────────────────
        from src.auto import run_auto
        run_auto(target=args.auto, model=args.model)

    else:
        # ── INTERACTIVE MODE ──────────────────────────────────────────────
        # Import here to avoid slow startup when just checking --help
        from main import main as interactive_main
        interactive_main()


if __name__ == "__main__":
    main()
