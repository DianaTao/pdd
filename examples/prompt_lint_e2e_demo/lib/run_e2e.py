#!/usr/bin/env python3
"""
End-to-end demo for ``pdd prompt lint`` on a **verifier LLM template**.

The ONLY hand-authored prompt is ``prompts/find_verification_errors_LLM.prompt``.
Fixture inputs under ``fixtures/`` are the (subject prompt, sample program, sample
code, sample output) tuple that the verifier template would evaluate when used as
an LLM — they are inputs, not answer keys.

Modes
-----
default (no API):
  Runs every command that does not require an LLM:
    pdd prompt lint
    pdd prompt lint --llm-template
    pdd contracts check --json
    pdd contracts compile --json
    pdd prompt lint --report formalization --json

--live (real API keys):
  Adds the LLM-driven chain on a work copy:
    pdd prompt lint --ambiguity --non-interactive --apply --json
    real verifier smoke run on fixtures (uses pdd.llm_invoke directly)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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

_PROMPT_NAME = "find_verification_errors_LLM.prompt"
_WORK_NAME = "find_verification_errors_work_LLM.prompt"

# Exit code reserved for "LLM unavailable" (over quota, auth-broken, no model
# in the fallback chain answered). Pytest live test maps this to skip().
_EXIT_LLM_UNAVAILABLE = 77


class _LLMUnavailable(RuntimeError):
    """Raised when every model in the fallback chain failed to answer."""


def _paths() -> dict[str, Path]:
    root = _DEMO_DIR
    fixtures = root / "fixtures"
    return {
        "prompt": root / "prompts" / _PROMPT_NAME,
        "work": root / "prompts" / _WORK_NAME,
        "reports": root / "reports",
        "subject_prompt": fixtures / "subject_refund_python.prompt",
        "sample_program": fixtures / "sample_program.py",
        "sample_code": fixtures / "sample_code.py",
        "sample_output": fixtures / "sample_output.txt",
    }


def _llm_configured() -> bool:
    if os.environ.get("PDD_MODEL_DEFAULT"):
        return True
    return any(
        os.environ.get(name)
        for name in (
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "AZURE_API_KEY",
            "VERTEXAI_PROJECT",
        )
    )


def _llm_preflight() -> tuple[bool, str]:
    """Do a tiny live LLM round-trip; return (ok, message)."""
    try:
        from pdd.llm_invoke import llm_invoke
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"could not import pdd.llm_invoke: {exc}"
    try:
        response = llm_invoke(
            prompt="Reply with the single word: ok",
            input_json={},
            strength=0.1,
            temperature=0.0,
            verbose=False,
        )
    except Exception as exc:
        return False, f"llm_invoke raised {type(exc).__name__}: {exc}"
    result = str(response.get("result", "")).strip()
    if not result:
        return False, "every model in the fallback chain returned empty output"
    return True, f"preflight ok via {response.get('model_name', '?')}"


def _has_vocabulary(path: Path) -> bool:
    return bool(
        re.search(r"<vocabulary>\s*\n\s*-\s+\S", path.read_text(encoding="utf-8"), re.I)
    )


def _has_formalization(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").lower()
    return "target: smt" in text or "z3" in text


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


def _hdr(title: str) -> None:
    print(f"\n{'=' * 64}\n  {title}\n{'=' * 64}")


def _lint_counts(stdout: str) -> tuple[int, int]:
    warn = re.search(r"(\d+)\s+warn", stdout)
    err = re.search(r"(\d+)\s+error", stdout)
    return int(warn.group(1)) if warn else 0, int(err.group(1)) if err else 0


def _step_prompt_lint(
    runner: CliRunner,
    prompt: Path,
    *,
    extra: list[str] | None = None,
    label: str,
) -> dict[str, Any]:
    args = ["--quiet", "prompt", "lint", *(extra or []), str(prompt.relative_to(_DEMO_DIR))]
    proc = _run_cli(runner, args, allow_warn_exit=True)
    warn, err = _lint_counts(proc.stdout)
    print(f"▶  pdd prompt lint {label}: {warn} warn, {err} error (exit {proc.returncode})")
    return {"exit_code": proc.returncode, "warn_count": warn, "error_count": err}


def _step_contracts_check(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    proc = _run_cli(
        runner,
        ["--quiet", "contracts", "check", "--json", str(prompt.relative_to(_DEMO_DIR))],
        allow_warn_exit=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pdd contracts check failed:\n{proc.stdout}")
    payload = _parse_json_stdout(proc.stdout)
    if not isinstance(payload, list):
        raise RuntimeError(f"contracts check expected list, got {type(payload)}")
    issue_count = sum(len(r.get("issues", [])) for r in payload)
    print(f"▶  pdd contracts check: {len(payload)} target(s), {issue_count} issue(s)")
    return {"results": payload, "issue_count": issue_count, "target_count": len(payload)}


def _step_contracts_compile(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    """pdd contracts compile --json (exit 2 with valid JSON is normal for vague input)."""
    proc = _run_cli(
        runner,
        ["--quiet", "contracts", "compile", "--json", str(prompt.relative_to(_DEMO_DIR))],
    )
    if proc.returncode not in (0, 2):
        raise RuntimeError(
            f"pdd contracts compile failed (code {proc.returncode}):\n{proc.stdout}"
        )
    payload = _parse_json_stdout(proc.stdout)
    rows = payload if isinstance(payload, list) else [payload]
    error_count = sum(row.get("error_count", 0) for row in rows)
    rule_count = sum(len(row.get("rules", []) or []) for row in rows)
    print(
        f"▶  pdd contracts compile: {rule_count} rule(s), "
        f"{error_count} compile error(s) (vague input expected)"
    )
    return {"payload": payload, "rule_count": rule_count, "error_count": error_count}


def _step_formalization(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    proc = _run_cli(
        runner,
        [
            "--quiet",
            "prompt",
            "lint",
            "--report",
            "formalization",
            "--json",
            str(prompt.relative_to(_DEMO_DIR)),
        ],
        allow_warn_exit=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"formalization report failed:\n{proc.stdout}")
    payload = _parse_json_stdout(proc.stdout)
    rows = payload if isinstance(payload, list) else payload.get("results", [])
    issue_count = sum(len(r.get("issues", [])) for r in rows)
    print(
        f"▶  pdd prompt lint --report formalization: "
        f"{len(rows)} file(s), {issue_count} formal issue(s)"
    )
    return {"payload": payload, "file_count": len(rows), "issue_count": issue_count}


def _step_clarify_apply(runner: CliRunner, prompt: Path) -> dict[str, Any]:
    """Real LLM: pdd prompt lint --ambiguity --non-interactive --apply --json."""
    proc = _run_cli(
        runner,
        [
            "--quiet",
            "prompt",
            "lint",
            "--ambiguity",
            "--non-interactive",
            "--apply",
            "--json",
            str(prompt.relative_to(_DEMO_DIR)),
        ],
        allow_warn_exit=True,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"pdd prompt lint --apply failed (code {proc.returncode}):\n{proc.stdout}"
        )
    if not proc.stdout.strip():
        raise _LLMUnavailable(
            "pdd prompt lint --apply returned no JSON — every LLM provider "
            "in the fallback chain failed (rate limit, auth, or unsupported "
            "model). Check Gemini quota and PDD_MODEL_DEFAULT."
        )
    payload = _parse_json_stdout(proc.stdout)
    guidance = payload.get("guidance", []) if isinstance(payload, dict) else []
    ambiguities = guidance[0].get("ambiguities", []) if guidance else []
    rejected = guidance[0].get("formalization_rejected", []) if guidance else []
    print(
        f"▶  pdd prompt lint --apply: {len(ambiguities)} ambiguity(ies), "
        f"{len(rejected)} formalization candidate(s) rejected"
    )
    return {
        "payload": payload,
        "ambiguity_count": len(ambiguities),
        "formalization_rejected_count": len(rejected),
    }


def _smoke_verify(work_prompt: Path, paths: dict[str, Path]) -> dict[str, Any]:
    """Real verifier smoke run using ``pdd.llm_invoke`` (no mocks)."""
    from pdd.llm_invoke import llm_invoke

    template = work_prompt.read_text(encoding="utf-8")
    input_json = {
        "program": paths["sample_program"].read_text(encoding="utf-8"),
        "prompt": paths["subject_prompt"].read_text(encoding="utf-8"),
        "code": paths["sample_code"].read_text(encoding="utf-8"),
        "output": paths["sample_output"].read_text(encoding="utf-8"),
    }
    try:
        response = llm_invoke(
            prompt=template,
            input_json=input_json,
            strength=0.5,
            temperature=0.0,
            verbose=False,
        )
    except Exception as exc:
        raise _LLMUnavailable(
            f"smoke verifier llm_invoke raised {type(exc).__name__}: {exc}"
        ) from exc
    raw = response.get("result", "{}")
    if not raw.strip():
        raise _LLMUnavailable(
            "smoke verifier got empty LLM response — every provider failed."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        data = json.loads(match.group(0)) if match else {"issues_count": -1, "details": raw}
    return {
        "issues_count": int(data.get("issues_count", -1)),
        "details_tail": str(data.get("details", ""))[-400:],
        "model_name": response.get("model_name"),
    }


def _write_report(report_dir: Path, name: str, payload: Any) -> None:
    report_dir.mkdir(exist_ok=True)
    (report_dir / f"{name}.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _cleanup(paths: dict[str, Path]) -> None:
    if paths["work"].exists():
        paths["work"].unlink()


def run_deterministic() -> int:
    paths = _paths()
    prompt = paths["prompt"]
    if not prompt.is_file():
        print(f"ERROR: missing input prompt {prompt}", file=sys.stderr)
        return 1
    if _has_vocabulary(prompt):
        print(
            f"ERROR: {_PROMPT_NAME} must stay vague (restore from git)",
            file=sys.stderr,
        )
        return 1

    os.chdir(_DEMO_DIR)
    runner = CliRunner()
    paths["reports"].mkdir(exist_ok=True)

    _hdr(f"① pdd prompt lint (`{_PROMPT_NAME}`)")
    lint = _step_prompt_lint(runner, prompt, label="(deterministic)")

    _hdr("② pdd prompt lint --llm-template (verifier template checks)")
    lint_tmpl = _step_prompt_lint(runner, prompt, extra=["--llm-template"], label="(template)")

    _hdr("③ pdd contracts check --json")
    contracts = _step_contracts_check(runner, prompt)

    _hdr("④ pdd contracts compile --json")
    compiled = _step_contracts_compile(runner, prompt)

    _hdr("⑤ pdd prompt lint --report formalization --json")
    formalization = _step_formalization(runner, prompt)

    _write_report(paths["reports"], "lint", lint)
    _write_report(paths["reports"], "lint_llm_template", lint_tmpl)
    _write_report(paths["reports"], "contracts_check", contracts)
    _write_report(paths["reports"], "contracts_compile", compiled)
    _write_report(paths["reports"], "formalization", formalization)
    _write_report(
        paths["reports"],
        "manifest",
        {
            "mode": "deterministic",
            "input_prompt": _PROMPT_NAME,
            "commands": [
                "pdd prompt lint",
                "pdd prompt lint --llm-template",
                "pdd contracts check --json",
                "pdd contracts compile --json",
                "pdd prompt lint --report formalization --json",
            ],
        },
    )

    _hdr("⑥ Summary")
    ok = (
        lint["warn_count"] > 0
        and contracts["issue_count"] > 0
        and compiled["error_count"] > 0
        and formalization["file_count"] >= 1
    )
    print(
        f"  lint warnings:        {lint['warn_count']}\n"
        f"  llm-template warns:   {lint_tmpl['warn_count']}\n"
        f"  contract issues:      {contracts['issue_count']}\n"
        f"  compile errors:       {compiled['error_count']}\n"
        f"  formalization issues: {formalization['issue_count']}"
    )
    if not ok:
        print(
            "\n  ERROR: expected CLI signals from the vague input were missing.",
            file=sys.stderr,
        )
        return 1
    print("\n  Deterministic E2E passed (real pdd CLI commands only).")
    return 0


def run_live(*, keep_artifacts: bool = False) -> int:
    paths = _paths()
    if not paths["prompt"].is_file():
        print(f"ERROR: missing {paths['prompt']}", file=sys.stderr)
        return 1
    if _has_vocabulary(paths["prompt"]):
        print(f"ERROR: {_PROMPT_NAME} must stay vague", file=sys.stderr)
        return 1
    for key in ("sample_program", "sample_code", "sample_output", "subject_prompt"):
        if not paths[key].is_file():
            print(f"ERROR: missing fixture {paths[key]}", file=sys.stderr)
            return 1
    if not _llm_configured():
        print(
            "ERROR: --live requires API credentials "
            "(e.g. OPENAI_API_KEY) or PDD_MODEL_DEFAULT.",
            file=sys.stderr,
        )
        return _EXIT_LLM_UNAVAILABLE

    _hdr("⓪ LLM preflight")
    ok, message = _llm_preflight()
    print(f"  {message}")
    if not ok:
        print(
            f"\n  SKIP: --live cannot run; exiting {_EXIT_LLM_UNAVAILABLE}.",
            file=sys.stderr,
        )
        return _EXIT_LLM_UNAVAILABLE

    os.chdir(_DEMO_DIR)
    runner = CliRunner()
    paths["reports"].mkdir(exist_ok=True)
    shutil.copyfile(paths["prompt"], paths["work"])
    snapshots: dict[str, Any] = {"mode": "live"}

    try:
        _hdr(f"① BEFORE — pdd prompt lint (`{_WORK_NAME}`)")
        before_lint = _step_prompt_lint(runner, paths["work"], label="(before clarify)")
        snapshots["before_lint"] = before_lint

        _hdr("② BEFORE — real smoke verify against fixtures/")
        print("  (real API call — no mocks)")
        try:
            before_smoke = _smoke_verify(paths["work"], paths)
        except _LLMUnavailable as exc:
            print(f"\n  SKIP: {exc}", file=sys.stderr)
            return _EXIT_LLM_UNAVAILABLE
        print(f"▶  smoke verifier → issues_count={before_smoke['issues_count']}")
        snapshots["before_smoke"] = before_smoke

        _hdr("③ pdd prompt lint --ambiguity --non-interactive --apply --json")
        try:
            clarify = _step_clarify_apply(runner, paths["work"])
        except _LLMUnavailable as exc:
            print(f"\n  SKIP: {exc}", file=sys.stderr)
            return _EXIT_LLM_UNAVAILABLE
        snapshots["clarify"] = {
            "ambiguity_count": clarify["ambiguity_count"],
            "formalization_rejected_count": clarify["formalization_rejected_count"],
        }
        if not _has_vocabulary(paths["work"]):
            print("ERROR: pdd prompt lint --apply did not write <vocabulary>", file=sys.stderr)
            return 1

        _hdr(f"④ AFTER — pdd prompt lint (clarified `{_WORK_NAME}`)")
        after_lint = _step_prompt_lint(runner, paths["work"], label="(after clarify)")
        snapshots["after_lint"] = after_lint

        _hdr("⑤ AFTER — real smoke verify against fixtures/")
        try:
            after_smoke = _smoke_verify(paths["work"], paths)
        except _LLMUnavailable as exc:
            print(f"\n  SKIP: {exc}", file=sys.stderr)
            return _EXIT_LLM_UNAVAILABLE
        print(f"▶  smoke verifier → issues_count={after_smoke['issues_count']}")
        snapshots["after_smoke"] = after_smoke

        snapshots["has_vocabulary_after"] = _has_vocabulary(paths["work"])
        snapshots["has_formalization_after"] = _has_formalization(paths["work"])

        _write_report(paths["reports"], "live", snapshots)

        _hdr("⑥ Comparison")
        print(
            f"  lint warnings:  {before_lint['warn_count']} → {after_lint['warn_count']}\n"
            f"  smoke issues:   {before_smoke['issues_count']} → {after_smoke['issues_count']}\n"
            f"  vocabulary:     no → {'yes' if snapshots['has_vocabulary_after'] else 'no'}\n"
            f"  formalization:  → {'yes' if snapshots['has_formalization_after'] else 'no'}"
        )

        ok = (
            clarify["ambiguity_count"] >= 1
            and snapshots["has_vocabulary_after"]
            and after_lint["warn_count"] <= before_lint["warn_count"]
        )
        if not ok:
            print("\n  ERROR: live success criteria not met.", file=sys.stderr)
            return 1
        print("\n  Live E2E passed (real pdd CLI + LLM).")
        return 0
    finally:
        if not keep_artifacts:
            _cleanup(paths)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "End-to-end demo of pdd prompt lint / pdd contracts on a verifier "
            "LLM template."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Real LLM clarify + real smoke verifier run (requires API keys).",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep ephemeral work copy after --live.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove ephemeral work copy and exit.",
    )
    args = parser.parse_args()

    if args.cleanup:
        _cleanup(_paths())
        print("Cleaned up demo artifacts.")
        return 0
    if args.live:
        return run_live(keep_artifacts=args.keep_artifacts)
    return run_deterministic()


if __name__ == "__main__":
    raise SystemExit(main())
