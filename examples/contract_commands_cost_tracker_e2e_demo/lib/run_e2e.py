#!/usr/bin/env python3
"""
E2E demo for ``pdd contracts`` commands on the cost_tracker prompt.

Demonstrates the contrast between a **baseline** prompt (no contracts) and a
**contracts-enriched** variant using the deterministic command pipeline:

  pdd prompt lint
  pdd contracts check
  pdd contracts compile
  pdd coverage --contracts

No LLM required for the default mode.

Modes
-----
default (no API)::

    bash demo.sh

--live (optional, real API keys)::

    bash demo.sh --live --keep-artifacts

--cleanup::

    bash demo.sh --cleanup
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEMO_DIR = Path(__file__).resolve().parent.parent

os.environ.setdefault("PDD_PATH", str(_REPO_ROOT / "pdd"))
os.environ.setdefault("PDD_SKIP_UPDATE_CHECK", "1")
os.environ.setdefault("PDD_ALLOW_DUPLICATE_RUN", "1")

from click.testing import CliRunner  # noqa: E402

from pdd import cli  # noqa: E402

_BASELINE_NAME = "cost_tracker_utility_Python.prompt"
_CONTRACTS_NAME = "cost_tracker_with_contracts_python.prompt"


def _paths() -> dict[str, Path]:
    root = _DEMO_DIR
    reports = root / "reports"
    return {
        "baseline": root / "prompts" / _BASELINE_NAME,
        "contracts": root / "prompts" / _CONTRACTS_NAME,
        "reports": reports,
        "stories": root / "user_stories",
        "tests_dir": root / "tests",
        "baseline_report": reports / "baseline.json",
        "contracts_report": reports / "contracts.json",
        "comparison": reports / "comparison.json",
    }


def _parse_json_stdout(stdout: str) -> Any:
    text = stdout.strip()
    for idx, ch in enumerate(text):
        if ch in "{[":
            try:
                return json.loads(text[idx:])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON in stdout (first 300 chars): {stdout[:300]!r}")


def _run_cli(
    runner: CliRunner,
    args: list[str],
    *,
    allow_warn_exit: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Invoke ``pdd ...`` via CliRunner; optionally treat exit 1 as success."""
    result = runner.invoke(cli.cli, args, catch_exceptions=True)
    output = result.output or ""
    code = result.exit_code if result.exit_code is not None else 0
    if allow_warn_exit and code == 1:
        code = 0
    return subprocess.CompletedProcess(args, code, output, "")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _hdr(title: str) -> None:
    print(f"\n{'=' * 64}\n  {title}\n{'=' * 64}")


def _sub(title: str) -> None:
    print(f"\n--- {title} ---")


# ---------------------------------------------------------------------------
# Per-prompt pipeline steps
# ---------------------------------------------------------------------------

def _step_lint(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    rel = str(prompt.relative_to(_DEMO_DIR))
    proc = _run_cli(runner, ["--quiet", "prompt", "lint", "--json", rel])
    payload = _parse_json_stdout(proc.stdout)
    issues = payload if isinstance(payload, list) else payload.get("issues", [])
    warn = sum(1 for i in issues if i.get("level") == "warning")
    err = sum(1 for i in issues if i.get("level") == "error")
    by_code: dict[str, int] = {}
    for issue in issues:
        by_code[issue.get("code", "?")] = by_code.get(issue.get("code", "?"), 0) + 1
    print(f"  pdd prompt lint: {warn} warn, {err} error (exit {proc.returncode})")
    return {"warn_count": warn, "error_count": err, "by_code": by_code, "exit_code": proc.returncode}


def _step_contracts_check(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    rel = str(prompt.relative_to(_DEMO_DIR))
    proc = _run_cli(
        runner,
        ["--quiet", "contracts", "check", "--json",
         "--stories", "user_stories", rel],
        allow_warn_exit=True,
    )
    payload = _parse_json_stdout(proc.stdout)
    results = payload if isinstance(payload, list) else [payload]
    total_issues = sum(len(r.get("issues", [])) for r in results)
    print(f"  pdd contracts check: {len(results)} target(s), {total_issues} issue(s) (exit {proc.returncode})")
    return {"result_count": len(results), "issue_count": total_issues,
            "exit_code": proc.returncode, "payload": results}


def _step_contracts_compile(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    rel = str(prompt.relative_to(_DEMO_DIR))
    proc = _run_cli(
        runner,
        ["--quiet", "contracts", "compile", "--json", rel],
        allow_warn_exit=True,
    )
    payload = _parse_json_stdout(proc.stdout)
    results = payload if isinstance(payload, list) else [payload]
    rule_count = sum(r.get("rule_count", 0) for r in results)
    obligation_count = sum(len(r.get("rules", [])) for r in results)
    error_count = sum(r.get("error_count", 0) for r in results)
    has_rules = any(r.get("has_contract_rules", False) for r in results)
    print(
        f"  pdd contracts compile: has_rules={has_rules} "
        f"rules={rule_count} obligations={obligation_count} errors={error_count} "
        f"(exit {proc.returncode})"
    )
    return {
        "has_contract_rules": has_rules,
        "rule_count": rule_count,
        "obligation_count": obligation_count,
        "compile_errors": error_count,
        "exit_code": proc.returncode,
        "payload": results,
    }


def _step_coverage(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    rel = str(prompt.relative_to(_DEMO_DIR))
    proc = _run_cli(
        runner,
        ["--quiet", "coverage", "--contracts", "--json",
         "--stories-dir", "user_stories", "--tests-dir", "tests", rel],
        allow_warn_exit=True,
    )
    payload = _parse_json_stdout(proc.stdout)
    rows = payload.get("results", []) if isinstance(payload, dict) else payload
    if not rows:
        print(f"  pdd coverage --contracts: no contract rules (legacy-safe)")
        return {"has_contract_rules": False, "rule_count": 0, "summary": {}, "exit_code": proc.returncode}
    summary = rows[0].get("summary", {})
    rule_count = len(rows[0].get("rules", []))
    has_rules = rows[0].get("has_contract_rules", False)
    print(
        f"  pdd coverage --contracts: has_rules={has_rules} {rule_count} rule(s) "
        f"checked={summary.get('checked', 0)} story_only={summary.get('story_only', 0)} "
        f"unchecked={summary.get('unchecked', 0)} (exit {proc.returncode})"
    )
    return {
        "has_contract_rules": has_rules,
        "rule_count": rule_count,
        "summary": summary,
        "exit_code": proc.returncode,
    }


# ---------------------------------------------------------------------------
# Full fixture run
# ---------------------------------------------------------------------------

def _run_fixture(runner: CliRunner, label: str, prompt: Path) -> dict[str, Any]:
    _hdr(f"{label.upper()} fixture: {prompt.name}")
    _sub(f"{label}: pdd prompt lint --json")
    lint = _step_lint(runner, prompt)
    _sub(f"{label}: pdd contracts check --json")
    check = _step_contracts_check(runner, prompt)
    _sub(f"{label}: pdd contracts compile --json")
    compile_ = _step_contracts_compile(runner, prompt)
    _sub(f"{label}: pdd coverage --contracts --json")
    coverage = _step_coverage(runner, prompt)
    return {
        "label": label,
        "prompt": prompt.name,
        "lint": lint,
        "check": check,
        "compile": compile_,
        "coverage": coverage,
        # Convenience flat fields for test assertions
        "lint_warn_count": lint["warn_count"],
        "lint_by_code": lint["by_code"],
        "check_issues": check["issue_count"],
        "has_contract_rules": compile_["has_contract_rules"],
        "compile_rules": compile_["rule_count"],
        "compile_errors": compile_["compile_errors"],
        "coverage_summary": coverage["summary"],
    }


# ---------------------------------------------------------------------------
# Comparison summary
# ---------------------------------------------------------------------------

def _print_comparison(rows: list[dict[str, Any]]) -> None:
    cols = [
        ("lint warns", lambda r: r["lint_warn_count"]),
        ("check issues", lambda r: r["check_issues"]),
        ("has contract rules", lambda r: r["has_contract_rules"]),
        ("compile rules", lambda r: r["compile_rules"]),
        ("compile errors", lambda r: r["compile_errors"]),
        ("coverage(checked/story/unchecked)", lambda r: (
            f"{r['coverage_summary'].get('checked', 0)}/"
            f"{r['coverage_summary'].get('story_only', 0)}/"
            f"{r['coverage_summary'].get('unchecked', 0)}"
        )),
    ]
    width = max(len(c) for c, _ in cols) + 2
    header = f"{'Metric':<{width}}" + "  ".join(f"{r['label']:>20}" for r in rows)
    print(f"\n{'-' * len(header)}\n{header}\n{'-' * len(header)}")
    for col_name, fn in cols:
        values = "  ".join(f"{str(fn(r)):>20}" for r in rows)
        print(f"{col_name:<{width}}{values}")
    print(f"{'-' * len(header)}\n")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(rows: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    baseline = next((r for r in rows if r["label"] == "baseline"), None)
    contracts = next((r for r in rows if r["label"] == "contracts"), None)

    if baseline and baseline.get("has_contract_rules"):
        failures.append("baseline prompt unexpectedly has contract rules")
    if contracts and not contracts.get("has_contract_rules"):
        failures.append("contracts prompt is missing contract rules")
    if contracts and contracts["compile_rules"] < 1:
        failures.append("contracts prompt has no compilable rules")
    if contracts:
        s = contracts.get("coverage_summary", {})
        total_covered = s.get("checked", 0) + s.get("story_only", 0)
        if total_covered < 1:
            failures.append("contracts prompt expected >=1 covered rule in coverage")

    return failures


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run_deterministic() -> int:
    paths = _paths()
    paths["reports"].mkdir(parents=True, exist_ok=True)

    os.chdir(_DEMO_DIR)
    runner = CliRunner()

    baseline_row = _run_fixture(runner, "baseline", paths["baseline"])
    contracts_row = _run_fixture(runner, "contracts", paths["contracts"])

    rows = [baseline_row, contracts_row]
    _print_comparison(rows)

    failures = _validate(rows)

    comparison = {
        "mode": "deterministic",
        "rows": rows,
        "validation_failures": failures,
    }
    _write_json(paths["comparison"], comparison)
    _write_json(paths["baseline_report"], baseline_row)
    _write_json(paths["contracts_report"], contracts_row)

    print(f"Reports written to {paths['reports']}")

    if failures:
        print(f"\n  Deterministic FAILED:\n" + "\n".join(f"    - {f}" for f in failures), file=sys.stderr)
        return 1

    print("\n  Deterministic PASSED.")
    return 0


def run_cleanup() -> int:
    paths = _paths()
    for path in [paths["comparison"], paths["baseline_report"], paths["contracts_report"]]:
        if path.exists():
            path.unlink()
    if paths["reports"].exists() and not any(paths["reports"].iterdir()):
        paths["reports"].rmdir()
    print("Cleaned up demo reports.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="E2E demo for pdd contracts commands on cost_tracker prompt.",
    )
    parser.add_argument("--live", action="store_true", help="(reserved for future LLM workflow)")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    if args.cleanup:
        return run_cleanup()

    if args.live:
        print("Note: --live mode not yet implemented for this demo. Running deterministic.")

    return run_deterministic()


if __name__ == "__main__":
    sys.exit(main())
