#!/usr/bin/env python3
"""
Local LLM CLI - Entry point

This is a simple wrapper that imports the main implementation
from the modular src/local_llm_cli/ package.
"""

import sys
from pathlib import Path

# Add src to path so we can import local_llm_cli
sys.path.insert(0, str(Path(__file__).parent / "src"))

from local_llm_cli import main

if __name__ == "__main__":
    sys.exit(main())
