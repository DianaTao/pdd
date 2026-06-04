#!/usr/bin/env python3
"""Touchpoint for #76 compressed sync context on the #876 marketplace dev unit.

CI mode builds phase packages locally (no LLM). ``--live`` runs ``pdd sync`` against
real PDD Cloud when authenticated.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

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

# Rough guide for --live (two full cloud syncs on a small dev unit).
_LIVE_SYNC_RUNS = 2
_LIVE_MINUTES_PER_SYNC = (5, 20)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _log(message: str, *, stream: TextIO | None = None) -> None:
    print(f"[{_ts()}] {message}", file=stream, flush=True)


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s"


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
    started = time.monotonic()
    _log("Building local compressed-sync-context packages (no LLM)...")
    _ensure_generated_code()
    phases = ["generate", "verify", "test", "fix"]
    reports = []
    for phase in phases:
        phase_started = time.monotonic()
        reports.append(_package_report(phase))
        row = reports[-1]
        _log(
            f"  phase={phase} used={row['used']} "
            f"chars={row['rendered_chars']} tokens={row.get('token_estimate')} "
            f"({_format_elapsed(time.monotonic() - phase_started)})"
        )
    generate = reports[0]
    fix = next(row for row in reports if row["phase"] == "fix")
    elapsed = time.monotonic() - started
    _log(f"Local touchpoint finished in {_format_elapsed(elapsed)}")
    return {
        "touchpoint": "compressed-sync-context-local",
        "prompt": str(PROMPT.relative_to(DEMO_DIR)),
        "duration_seconds": round(elapsed, 2),
        "phases": reports,
        "checks": {
            "all_phases_used": all(row["used"] for row in reports),
            "generate_smaller_than_fix": (generate["rendered_chars"] or 0)
            <= (fix["rendered_chars"] or 0),
            "generate_has_tokens": bool(generate.get("token_estimate")),
        },
    }


def _run_live_sync(*, compressed: bool, run_index: int, run_total: int) -> dict[str, Any]:
    label = "compressed-context ON" if compressed else "compressed-context OFF (baseline)"
    cmd = [
        "pdd",
        "--force",
        "sync",
        "ticket_classifier",
        "--evidence",
        "--no-steer",
        "--compress",
        "--compress-examples",
    ]
    if compressed:
        cmd.append("--compressed-context")
    else:
        cmd.append("--no-compressed-context")

    _log(
        f"Live sync run {run_index}/{run_total}: {label} "
        f"(expect ~{_LIVE_MINUTES_PER_SYNC[0]}–{_LIVE_MINUTES_PER_SYNC[1]} min; "
        "generate → verify → test → fix depends on cloud + model)"
    )
    _log(f"  command: {' '.join(cmd)}")
    _log("  streaming pdd output below (no output yet = still working)...")

    started = time.monotonic()
    captured: list[str] = []
    # pdd auto_update() blocks on input("Would you like to upgrade?") when a newer
    # PyPI version exists and stdin is a TTY — subprocess inherits the terminal.
    env = {
        **os.environ,
        "PDD_AUTO_UPDATE": "false",
        "PDD_SKIP_UPDATE_CHECK": "1",
        "PYTHONUNBUFFERED": "1",
        "CI": "1",
    }
    proc = subprocess.Popen(
        cmd,
        cwd=DEMO_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        captured.append(line)
    returncode = proc.wait()
    elapsed = time.monotonic() - started
    combined = "".join(captured)
    status = "OK" if returncode == 0 else f"FAILED (exit {returncode})"
    _log(f"Live sync run {run_index}/{run_total} finished: {status} in {_format_elapsed(elapsed)}")

    return {
        "compressed_context": compressed,
        "label": label,
        "returncode": returncode,
        "duration_seconds": round(elapsed, 2),
        "stdout_tail": combined[-4000:],
        "stderr_tail": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Timing: local mode is sub-second. --live runs two full pdd sync invocations; "
            f"plan ~{_LIVE_MINUTES_PER_SYNC[0] * _LIVE_SYNC_RUNS}–"
            f"{_LIVE_MINUTES_PER_SYNC[1] * _LIVE_SYNC_RUNS} minutes total "
            "(varies with model, fix loops, and marketplace retrieval)."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run real pdd sync (requires pdd auth login and API access).",
    )
    parser.add_argument(
        "--single-run",
        action="store_true",
        help=(
            "With --live: run only one sync with --compressed-context (~5–20 min). "
            "Use after run_demo_live.sh for marketplace/generate baseline."
        ),
    )
    args = parser.parse_args()
    if args.single_run and not args.live:
        parser.error("--single-run requires --live")

    overall_started = time.monotonic()
    _log("Compressed sync context touchpoint (#76 on #876 fixtures)")
    live_run_plan: list[tuple[bool, str]] = [(False, "baseline"), (True, "compressed")]
    if args.live:
        if args.single_run:
            live_run_plan = [(True, "compressed-only")]
            _log(
                "--live --single-run: one cloud sync with --compressed-context "
                f"(~{_LIVE_MINUTES_PER_SYNC[0]}–{_LIVE_MINUTES_PER_SYNC[1]} min)"
            )
        else:
            low = _LIVE_MINUTES_PER_SYNC[0] * _LIVE_SYNC_RUNS
            high = _LIVE_MINUTES_PER_SYNC[1] * _LIVE_SYNC_RUNS
            _log(
                f"--live enabled: {_LIVE_SYNC_RUNS} cloud sync runs; "
                f"typical wall time ~{low}–{high} minutes (logged per run)"
            )

    payload: dict[str, Any] = {"local": _run_local_touchpoint()}
    if args.live:
        live_runs: list[dict[str, Any]] = []
        run_total = len(live_run_plan)
        for index, (compressed, _tag) in enumerate(live_run_plan, start=1):
            live_runs.append(
                _run_live_sync(
                    compressed=compressed,
                    run_index=index,
                    run_total=run_total,
                )
            )
        payload["live_sync_mode"] = "single-run" if args.single_run else "full-compare"
        payload["live_sync"] = live_runs
        total_live = sum(r.get("duration_seconds", 0) for r in live_runs)
        payload["live_sync_total_seconds"] = round(total_live, 2)
        _log(f"All live sync runs finished in {_format_elapsed(total_live)}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload["total_duration_seconds"] = round(time.monotonic() - overall_started, 2)
    REPORT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    checks = payload["local"]["checks"]
    _log(f"Report written: {REPORT.relative_to(REPO_ROOT)}")
    if not checks["all_phases_used"]:
        _log("FAIL: one or more phases did not use compressed context", stream=sys.stderr)
        return 1
    if args.live:
        for row in payload.get("live_sync", []):
            if row.get("returncode") != 0:
                _log(
                    f"FAIL: live sync ({row.get('label')}) exit {row.get('returncode')}",
                    stream=sys.stderr,
                )
                return 1
    _log(
        f"PASS in {_format_elapsed(payload['total_duration_seconds'])} "
        "(local packages"
        + (
            ", live sync OK"
            if args.live
            else ""
        )
        + ")"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
