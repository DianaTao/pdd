#!/usr/bin/env python3
"""Verification program for pdd sync on the ticket classifier dev unit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    demo_dir = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(demo_dir / "tests")],
        cwd=demo_dir,
        check=False,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
