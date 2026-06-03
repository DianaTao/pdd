"""Integration test for the prompt compression few-shot demo fixtures."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from pdd.preprocess import preprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "examples" / "prompt_compression_few_shot_demo"
FIXTURES = DEMO_DIR / "fixtures"
PROMPT = FIXTURES / "classify_issues.prompt"

FEW_SHOT_MARKERS = (
    'Input: "The app crashes when I click Save."',
    'Output: {"category": "bug", "severity": "high"}',
)
SCHEMA_MARKERS = (
    "Return JSON with keys:",
    "severity: one of low | medium | high",
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expand(*, compress: bool, monkeypatch: pytest.MonkeyPatch | None = None) -> str:
    if compress:
        if monkeypatch is not None:
            monkeypatch.setenv("PDD_CONTEXT_COMPRESSION", "contracts")
        else:
            import os

            os.environ["PDD_CONTEXT_COMPRESSION"] = "contracts"
    elif monkeypatch is not None:
        monkeypatch.delenv("PDD_CONTEXT_COMPRESSION", raising=False)
    return preprocess(
        PROMPT.read_text(encoding="utf-8"),
        recursive=False,
        double_curly_brackets=False,
        compress=compress,
    )


def test_prompt_compression_preserves_few_shot_and_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compression shortens redundant context but keeps few-shot I/O and schema."""
    monkeypatch.chdir(REPO_ROOT)
    baseline = _expand(compress=False, monkeypatch=monkeypatch)
    compressed = _expand(compress=True, monkeypatch=monkeypatch)
    again = _expand(compress=True, monkeypatch=monkeypatch)

    assert len(compressed) < len(baseline)
    assert compressed == again
    assert all(marker in compressed for marker in FEW_SHOT_MARKERS)
    assert all(marker in compressed for marker in SCHEMA_MARKERS)
    assert "def classify_issue(" in compressed
    assert '"""Few-shot mold' not in compressed
    assert "<pdd-interface>" in compressed
    assert _sha256(compressed) == _sha256(again)


def test_prompt_compression_demo_script_runs() -> None:
    """The runnable demo exits cleanly and reports PASS checks."""
    proc = subprocess.run(
        [sys.executable, str(DEMO_DIR / "run_demo.py")],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[PASS] compressed shorter than uncompressed baseline" in proc.stdout
    assert "[PASS] few-shot Input/Output pairs preserved" in proc.stdout
