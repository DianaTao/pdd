"""Integration test for representative marketplace compression regeneration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "examples" / "marketplace_compression_regeneration_demo"
REPORT = DEMO_DIR / "generated" / "marketplace_compression_report.json"


def test_marketplace_compression_regeneration_demo_runs() -> None:
    """Representative marketplace few-shot compression still regenerates valid code."""
    proc = subprocess.run(
        [sys.executable, str(DEMO_DIR / "run_demo.py")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Behavior checks: PASS" in proc.stdout
    assert "examples used" in proc.stdout.lower()

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    uncompressed, compressed = report["runs"]

    assert uncompressed["mode"] == "uncompressed"
    assert compressed["mode"] == "compressed"
    assert uncompressed["behavior_passed"] is True
    assert compressed["behavior_passed"] is True
    assert report["reduction"]["final_prompt_chars"] > 0
    assert report["reduction"]["final_estimated_tokens"] > 0
    assert (
        compressed["cloud_prompt_stats"]["finalPromptChars"]
        < uncompressed["cloud_prompt_stats"]["finalPromptChars"]
    )
    assert compressed["examples_used"]
    assert all(
        example.get("source") == "marketplace"
        for example in compressed["examples_used"]
    )
    assert report["execution_mode"] == "representative"
    assert report["benchmark_criteria"]["compression_compare"]
    assert report["reduction"]["expanded_prompt_chars"] > 0
    assert report["reduction"]["marketplace_few_shot_chars"] > 0
