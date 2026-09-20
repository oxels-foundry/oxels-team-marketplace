#!/usr/bin/env python3
"""Run the bundled redline_guard CLI from any working directory."""

from __future__ import annotations

import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from redline_guard.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
