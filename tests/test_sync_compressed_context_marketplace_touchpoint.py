"""CI touchpoint: compressed sync context packages on marketplace demo fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "examples" / "marketplace_compression_regeneration_demo"
REPORT = DEMO_DIR / "generated" / "sync_compressed_context_report.json"
SCRIPT = DEMO_DIR / "run_sync_compressed_touchpoint.py"


def test_sync_compressed_context_marketplace_touchpoint() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS: local compressed-sync-context" in proc.stdout

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["local"]["checks"]["all_phases_used"] is True
    phases = {row["phase"]: row for row in report["local"]["phases"]}
    assert phases["generate"]["used"] is True
    assert phases["verify"]["used"] is True
    assert phases["fix"]["used"] is True
    assert phases["generate"]["token_estimate"] > 0
