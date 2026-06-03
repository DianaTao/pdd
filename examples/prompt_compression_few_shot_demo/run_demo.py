#!/usr/bin/env python3
"""Human-verifiable demo: prompt compression preserves few-shot behavioral contracts."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pdd.preprocess import preprocess  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROMPT = FIXTURES / "classify_issues.prompt"

FEW_SHOT_MARKERS = (
    'Input: "The app crashes when I click Save."',
    'Output: {"category": "bug", "severity": "high"}',
    'Input: "Can you add dark mode?"',
    'Output: {"category": "feature_request", "severity": "medium"}',
    'Input: "The README is missing install steps."',
    'Output: {"category": "documentation", "severity": "low"}',
    'Input: "Dashboard feels slow on mobile."',
    'Output: {"category": "usability", "severity": "medium"}',
)
SCHEMA_MARKERS = (
    "Return JSON with keys:",
    "category: one of bug | feature_request | documentation | usability | other",
    "severity: one of low | medium | high",
)
EXECUTABLE_MARKERS = (
    "def classify_issue(",
    "def format_issue_json(",
    '"category": "bug"',
    '"severity": "high"',
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expand(*, compress: bool) -> str:
    original = PROMPT.read_text(encoding="utf-8")
    if compress:
        os.environ["PDD_CONTEXT_COMPRESSION"] = "contracts"
    else:
        os.environ.pop("PDD_CONTEXT_COMPRESSION", None)
    return preprocess(
        original,
        recursive=False,
        double_curly_brackets=False,
        compress=compress,
    )


def main() -> int:
    os.chdir(REPO_ROOT)
    original = PROMPT.read_text(encoding="utf-8")
    baseline = _expand(compress=False)
    compressed = _expand(compress=True)
    compressed_repeat = _expand(compress=True)

    print("=== Prompt compression few-shot demo ===")
    print(f"Fixture prompt: {PROMPT.relative_to(REPO_ROOT)}")
    print(f"Original (with include tags): {len(original)} chars")
    print(f"Expanded baseline (compress=False): {len(baseline)} chars")
    print(f"Expanded compressed (compress=True): {len(compressed)} chars")
    print(f"Reduction vs baseline: {len(baseline) - len(compressed)} chars")
    print()

    checks: list[tuple[str, bool]] = [
        ("compressed shorter than uncompressed baseline", len(compressed) < len(baseline)),
        ("deterministic across runs", compressed == compressed_repeat),
        ("few-shot Input/Output pairs preserved", all(m in compressed for m in FEW_SHOT_MARKERS)),
        ("output schema preserved", all(m in compressed for m in SCHEMA_MARKERS)),
        ("compressed Python mold keeps executable logic", all(m in compressed for m in EXECUTABLE_MARKERS)),
        ("docstrings stripped from included Python", '"""Few-shot mold' not in compressed),
        ("redundant markdown anecdotes removed", "Some issues mention coffee machines." not in compressed),
        ("grounding metadata preserved", "<pdd-interface>" in compressed),
    ]

    print("Checks:")
    failed = False
    for label, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        failed = failed or not ok

    print()
    print(f"Compressed SHA-256: {_sha256(compressed)}")
    print()
    print("--- Uncompressed baseline (excerpt) ---")
    print(baseline[:700] + ("..." if len(baseline) > 700 else ""))
    print()
    print("--- Compressed prompt (excerpt) ---")
    print(compressed[:700] + ("..." if len(compressed) > 700 else ""))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
