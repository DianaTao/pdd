#!/usr/bin/env python3
"""Touchpoint for #76 compressed sync context on the #876 marketplace dev unit.

CI mode builds phase packages locally (no LLM). ``--live`` runs ``pdd sync`` against
real PDD Cloud when authenticated.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pdd.compressed_sync_context import (  # noqa: E402
    build_compressed_sync_context,
    metadata,
    render_for_prompt,
)

DEMO_DIR = Path(__file__).resolve().parent
PROMPT = DEMO_DIR / "prompts" / "ticket_classifier_python.prompt"
CODE = DEMO_DIR / "generated" / "ticket_classifier.py"
EXAMPLE = DEMO_DIR / "examples" / "ticket_classifier_example.py"
TESTS = [DEMO_DIR / "tests" / "test_ticket_classifier.py"]
REPORT = DEMO_DIR / "generated" / "sync_compressed_context_report.json"
MOLD = DEMO_DIR / "fixtures" / "ticket_classifier_mold.py"


def _ensure_generated_code() -> None:
    CODE.parent.mkdir(parents=True, exist_ok=True)
    if not CODE.is_file():
        shutil.copy2(MOLD, CODE)


def _package_report(phase: str) -> dict[str, Any]:
    package = build_compressed_sync_context(
        phase,
        PROMPT,
        code_path=CODE,
        example_path=EXAMPLE,
        test_paths=TESTS,
    )
    rendered = render_for_prompt(package)
    meta = metadata(package)
    return {
        "phase": phase,
        "used": package.used,
        "rendered_chars": len(rendered),
        "token_estimate": meta.get("token_estimate"),
        "char_count": meta.get("char_count"),
        "compressed_sha256": meta.get("compressed_sha256"),
        "source_count": meta.get("source_count"),
        "missing_sources": package.missing_sources,
    }


def _run_local_touchpoint() -> dict[str, Any]:
    _ensure_generated_code()
    phases = ["generate", "verify", "test", "fix"]
    reports = [_package_report(phase) for phase in phases]
    generate = reports[0]
    fix = next(row for row in reports if row["phase"] == "fix")
    return {
        "touchpoint": "compressed-sync-context-local",
        "prompt": str(PROMPT.relative_to(DEMO_DIR)),
        "phases": reports,
        "checks": {
            "all_phases_used": all(row["used"] for row in reports),
            "generate_smaller_than_fix": (generate["rendered_chars"] or 0)
            <= (fix["rendered_chars"] or 0),
            "generate_has_tokens": bool(generate.get("token_estimate")),
        },
    }


def _run_live_sync(*, compressed: bool) -> dict[str, Any]:
    cmd = [
        "pdd",
        "sync",
        "ticket_classifier",
        "--force",
        "--evidence",
        "-y",
        "--compress",
        "--compress-examples",
    ]
    if compressed:
        cmd.append("--compressed-context")
    else:
        cmd.append("--no-compressed-context")
    proc = subprocess.run(
        cmd,
        cwd=DEMO_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "compressed_context": compressed,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run real pdd sync (requires pdd auth login and API access).",
    )
    args = parser.parse_args()

    payload: dict[str, Any] = {"local": _run_local_touchpoint()}
    if args.live:
        payload["live_sync"] = [
            _run_live_sync(compressed=False),
            _run_live_sync(compressed=True),
        ]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    checks = payload["local"]["checks"]
    print("Compressed sync context touchpoint (#76 on #876 fixtures)")
    for row in payload["local"]["phases"]:
        print(
            f"  {row['phase']}: used={row['used']} "
            f"chars={row['rendered_chars']} tokens={row.get('token_estimate')}"
        )
    print(f"Report: {REPORT.relative_to(REPO_ROOT)}")
    if not checks["all_phases_used"]:
        print("FAIL: one or more phases did not use compressed context", file=sys.stderr)
        return 1
    if args.live and any(r["returncode"] != 0 for r in payload.get("live_sync", [])):
        print("FAIL: live sync returned non-zero", file=sys.stderr)
        return 1
    print("PASS: local compressed-sync-context packages built for all phases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
