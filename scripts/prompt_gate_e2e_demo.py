#!/usr/bin/env python3
"""End-to-end demo for the prompt-aware checkup + automatic prompt gate (PR #1428, #1420).

This drives the **real** ``pdd checkup``, ``pdd change`` and ``pdd generate`` CLIs
against disposable fixture projects, in real subprocesses, and prints a transcript
(command, changed prompt path, gate output, exit code) for each scenario. The only
thing stubbed is the model/provider boundary (see ``tests/e2e/_fake_provider_cli``);
the prompt gate, ``change_main``, gate-mode resolution from ``.pddrc`` and the
source-set report all run for real.

Run it directly to print the transcript and get a pass/fail summary::

    python scripts/prompt_gate_e2e_demo.py

It exits non-zero if any scenario's real exit code does not match expectations,
so it doubles as a smoke test. ``tests/e2e/test_prompt_gate_workflow.py`` imports
the scenario runners below and asserts on the same structured results.

Scenarios
---------
* ``checkup``        — ``pdd checkup <prompt> --json`` on a clean prompt (no mocks).
* ``checkup-nested`` — ``pdd checkup --project-root <proj> <proj>/prompts/...`` from an
  **external** cwd, proving the coverage lookup is anchored to the project root and
  not the process cwd (the #1428 rooting fix), in a real user-style invocation.
* ``change-warn``    — ``pdd change --manual ...`` with ``.pddrc prompt_gate: warn``:
  gate reports findings but the run continues (exit 0).
* ``change-strict``  — same with ``--prompt-checkup strict``: gate blocks (exit 2).
* ``generate-warn``  — ``pdd generate <issue> --prompt-checkup warn``: gate reports,
  continues (exit 0).
* ``generate-strict``— ``pdd generate <issue>`` with ``.pddrc prompt_gate: strict``
  (unquoted ``off``/``strict`` also exercises the YAML-scalar config path): gate
  blocks (exit 2).
* ``change-off``     — ``.pddrc`` with unquoted ``prompt_gate: off`` (PyYAML loads it
  as boolean ``False``): gate is skipped (exit 0), validating config-based disabling.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "prompt_lint"
ENTRYPOINT = REPO_ROOT / "tests" / "e2e" / "_fake_provider_cli.py"

# A prompt with undefined vague terms → deterministic lint warnings (no errors).
VAGUE_PROMPT = (FIXTURES / "vague_undefined.prompt").read_text(encoding="utf-8")
# A clean prompt whose <contract_rules> R1..R5 are covered by story__payment_api.md.
CLEAN_PROMPT = (FIXTURES / "payment_api_clean_python.prompt").read_text(encoding="utf-8")
PAYMENT_STORY = (FIXTURES / "story__payment_api.md").read_text(encoding="utf-8")


@dataclass
class ScenarioResult:
    """Outcome of one real CLI run."""

    name: str
    command: str
    exit_code: int
    expected_exit_code: int
    changed_prompts: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    notes: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == self.expected_exit_code

    def gate_excerpt(self, limit: int = 12) -> str:
        """Lines from stdout that evidence the gate ran after the prompt write."""
        keep: list[str] = []
        for line in self.stdout.splitlines():
            if any(
                marker in line
                for marker in (
                    "Prompt checkup",
                    "Prompt:",
                    "Status:",
                    "Findings:",
                    "saved to",
                    "Next:",
                    "blocked",
                    '"schema"',
                    '"status"',
                )
            ):
                keep.append(line.rstrip())
            if len(keep) >= limit:
                break
        return "\n".join(keep)


def _cli_env(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PDD_PATH": str(REPO_ROOT / "pdd"),
            "PYTHONPATH": str(REPO_ROOT),
            "PDD_AUTO_UPDATE": "false",
            "PDD_NO_GITHUB_STATE": "1",
        }
    )
    if extra:
        env.update(extra)
    return env


def _write_pddrc(project: Path, gate_mode: str, *, quote: bool = True) -> None:
    """Write a minimal valid .pddrc setting checkup.prompt_gate.

    ``quote=False`` writes the value unquoted (e.g. ``prompt_gate: off``) so the
    YAML scalar/boolean handling in the config loader is exercised end-to-end.
    """
    value = f'"{gate_mode}"' if quote else gate_mode
    project.joinpath(".pddrc").write_text(
        "version: 1\n"
        "contexts:\n"
        "  default:\n"
        "    paths:\n"
        "      prompts: prompts\n"
        "checkup:\n"
        f"  prompt_gate: {value}\n",
        encoding="utf-8",
    )


def _git_init(project: Path) -> None:
    """Give the fixture a strong project-root marker (.git) for deterministic rooting."""
    subprocess.run(
        ["git", "init", "-q"],
        cwd=project,
        check=False,
        capture_output=True,
    )


def make_project(
    base: Path,
    *,
    gate_mode: str = "warn",
    quote_mode: bool = True,
    with_coverage: bool = False,
) -> Path:
    """Create a disposable fixture project with prompts/, .pddrc and (optionally) coverage."""
    project = base / "proj"
    (project / "prompts").mkdir(parents=True)
    _write_pddrc(project, gate_mode, quote=quote_mode)
    if with_coverage:
        (project / "user_stories").mkdir()
        (project / "tests").mkdir()
        (project / "user_stories" / "story__payment_api.md").write_text(
            PAYMENT_STORY, encoding="utf-8"
        )
    _git_init(project)
    return project


# --------------------------------------------------------------------------- #
# Scenario runners. Each returns a ScenarioResult from a real subprocess.
# --------------------------------------------------------------------------- #


def run_checkup_clean(base: Path) -> ScenarioResult:
    """pdd checkup on a clean prompt fixture — fully real, no mocks."""
    prompt = FIXTURES / "clean.prompt"
    cmd = [sys.executable, "-m", "pdd.cli", "checkup", str(prompt), "--json"]
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, env=_cli_env(), capture_output=True, text=True, check=False
    )
    return ScenarioResult(
        name="checkup",
        command="pdd checkup tests/fixtures/prompt_lint/clean.prompt --json",
        exit_code=proc.returncode,
        expected_exit_code=proc.returncode if proc.returncode in {0, 1} else -1,
        stdout=proc.stdout,
        stderr=proc.stderr,
        notes="schema/JSON smoke; exit 0 (pass) or 1 (warn) both acceptable",
    )


def run_checkup_nested(base: Path) -> ScenarioResult:
    """pdd checkup --project-root <proj> from an EXTERNAL cwd → coverage anchored to root.

    The prompt (R1..R5) and its covering story live under <proj>; we invoke from the
    repo root (an unrelated cwd). With the #1428 fix the story is found via the
    project root, so the rules are 'story-only' rather than 'unchecked'.
    """
    project = base / "nested"
    (project / "prompts").mkdir(parents=True)
    (project / "user_stories").mkdir()
    (project / "tests").mkdir()
    prompt = project / "prompts" / "payment_api_clean_python.prompt"
    prompt.write_text(CLEAN_PROMPT, encoding="utf-8")
    (project / "user_stories" / "story__payment_api.md").write_text(
        PAYMENT_STORY, encoding="utf-8"
    )
    _write_pddrc(project, "warn")
    _git_init(project)

    cmd = [
        sys.executable,
        "-m",
        "pdd.cli",
        "checkup",
        "--project-root",
        str(project),
        str(prompt),
        "--json",
    ]
    # cwd is the repo root: deliberately NOT the project, to prove rooting.
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, env=_cli_env(), capture_output=True, text=True, check=False
    )
    unchecked = _coverage_unchecked_count(proc.stdout)
    note = (
        f"coverage 'unchecked' rules from external cwd: {unchecked} "
        "(0 ⇒ story under project root was found ⇒ rooting fix works)"
    )
    return ScenarioResult(
        name="checkup-nested",
        command=(
            "cd <repo-root> && pdd checkup --project-root <proj> "
            "<proj>/prompts/payment_api_clean_python.prompt --json"
        ),
        exit_code=proc.returncode,
        # 0 (pass) or 1 (warn) acceptable; the real assertion is unchecked == 0.
        expected_exit_code=proc.returncode if proc.returncode in {0, 1} else -1,
        stdout=proc.stdout,
        stderr=proc.stderr,
        notes=note,
    )


def _coverage_unchecked_count(stdout: str) -> Optional[int]:
    """Count contract-coverage findings flagged 'unchecked' in a checkup JSON payload."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    reports = payload.get("reports") or [payload]
    count = 0
    for report in reports:
        for finding in report.get("findings", []):
            if finding.get("source_check") == "coverage" and finding.get("code") == "unchecked":
                count += 1
    return count


def _run_entrypoint(
    pdd_args: list[str], *, cwd: Path, env_extra: dict[str, str]
) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(ENTRYPOINT), *pdd_args]
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=_cli_env(env_extra),
        capture_output=True,
        text=True,
        check=False,
    )


def run_change_manual(base: Path, *, gate_mode: str, cli_flag: Optional[str]) -> ScenarioResult:
    """Real ``pdd change --manual`` writing a .prompt, then the REAL gate.

    Only the model (change_func) and path/config plumbing are stubbed via the
    entrypoint; change_main and the gate run for real.
    """
    quote = gate_mode != "off"  # write `off` unquoted to exercise YAML scalar handling
    project = make_project(base, gate_mode=gate_mode, quote_mode=quote)
    change_prompt = project / "change_python.prompt"
    change_prompt.write_text("% Tighten the wording.\n", encoding="utf-8")
    input_code = project / "module.py"
    input_code.write_text("def handler():\n    return 1\n", encoding="utf-8")
    input_prompt = project / "prompts" / "feature_python.prompt"
    input_prompt.write_text(VAGUE_PROMPT, encoding="utf-8")
    out_prompt = project / "prompts" / "feature_python.prompt"  # overwrite in place

    pdd_args = [
        "change",
        "--manual",
        str(change_prompt),
        str(input_code),
        str(input_prompt),
        "--output",
        str(out_prompt),
    ]
    if cli_flag:
        pdd_args += ["--prompt-checkup", cli_flag]

    proc = _run_entrypoint(pdd_args, cwd=project, env_extra={})
    expected = 2 if (cli_flag == "strict" or gate_mode == "strict") else 0
    mode_src = f"--prompt-checkup {cli_flag}" if cli_flag else f".pddrc prompt_gate: {gate_mode}"
    return ScenarioResult(
        name=f"change-{cli_flag or gate_mode}",
        command="pdd change --manual change_python.prompt module.py feature_python.prompt "
        f"--output prompts/feature_python.prompt ({mode_src})",
        exit_code=proc.returncode,
        expected_exit_code=expected,
        changed_prompts=[str(out_prompt.relative_to(project))],
        stdout=proc.stdout,
        stderr=proc.stderr,
        notes=f"gate mode via {mode_src}",
    )


def run_generate_agentic(base: Path, *, gate_mode: str, cli_flag: Optional[str]) -> ScenarioResult:
    """Real ``pdd generate <issue>`` whose orchestrator writes a .prompt, then the REAL gate."""
    quote = gate_mode != "off"
    project = make_project(base, gate_mode=gate_mode, quote_mode=quote)
    gen_prompt = project / "prompts" / "new_feature_python.prompt"
    text_file = base / "gen_prompt_text.prompt"
    text_file.write_text(VAGUE_PROMPT, encoding="utf-8")

    pdd_args = [
        "generate",
        "https://github.com/example/repo/issues/1",
        "--no-github-state",
    ]
    if cli_flag:
        pdd_args += ["--prompt-checkup", cli_flag]

    env_extra = {
        "PDD_E2E_GEN_PROMPT_PATH": str(gen_prompt),
        "PDD_E2E_PROMPT_TEXT_FILE": str(text_file),
    }
    proc = _run_entrypoint(pdd_args, cwd=project, env_extra=env_extra)
    expected = 2 if (cli_flag == "strict" or gate_mode == "strict") else 0
    mode_src = f"--prompt-checkup {cli_flag}" if cli_flag else f".pddrc prompt_gate: {gate_mode}"
    return ScenarioResult(
        name=f"generate-{cli_flag or gate_mode}",
        command=f"pdd generate <issue-url> --no-github-state ({mode_src})",
        exit_code=proc.returncode,
        expected_exit_code=expected,
        changed_prompts=[str(gen_prompt.relative_to(project))],
        stdout=proc.stdout,
        stderr=proc.stderr,
        notes=f"orchestrator wrote {gen_prompt.name}; gate mode via {mode_src}",
    )


def all_scenarios(base: Path) -> list[ScenarioResult]:
    """Run every scenario in its own disposable sub-project under *base*."""
    results: list[ScenarioResult] = []
    results.append(run_checkup_clean(base / "s_checkup"))
    (base / "s_checkup").mkdir(exist_ok=True)
    results.append(run_checkup_nested(base / "s_nested"))
    results.append(run_change_manual(base / "s_change_warn", gate_mode="warn", cli_flag=None))
    results.append(run_change_manual(base / "s_change_strict", gate_mode="warn", cli_flag="strict"))
    results.append(run_change_manual(base / "s_change_off", gate_mode="off", cli_flag=None))
    results.append(run_generate_agentic(base / "s_gen_warn", gate_mode="warn", cli_flag="warn"))
    results.append(run_generate_agentic(base / "s_gen_strict", gate_mode="strict", cli_flag=None))
    return results


def _print_transcript(results: list[ScenarioResult]) -> None:
    for res in results:
        status = "PASS" if res.ok else "FAIL"
        print("=" * 78)
        print(f"[{status}] {res.name}")
        print(f"  $ {res.command}")
        if res.changed_prompts:
            print(f"  changed .prompt: {', '.join(res.changed_prompts)}")
        print(f"  exit code: {res.exit_code} (expected {res.expected_exit_code})")
        if res.notes:
            print(f"  note: {res.notes}")
        excerpt = res.gate_excerpt()
        if excerpt:
            print("  --- gate / report output ---")
            for line in excerpt.splitlines():
                print(f"  | {line}")
    print("=" * 78)


def main(argv: Optional[list[str]] = None) -> int:
    base = Path(tempfile.mkdtemp(prefix="pdd-e2e-gate-"))
    try:
        results = all_scenarios(base)
        _print_transcript(results)
        failures = [r for r in results if not r.ok]
        print(
            f"\nSummary: {len(results) - len(failures)}/{len(results)} scenarios "
            f"matched expected exit codes."
        )
        # The nested scenario additionally asserts coverage is anchored to the root.
        nested = next((r for r in results if r.name == "checkup-nested"), None)
        if nested is not None and "unchecked" in nested.notes and "0 " not in nested.notes:
            print(
                "WARNING: nested checkup still reports 'unchecked' coverage from an "
                "external cwd — rooting fix did not take effect."
            )
        return 1 if failures else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
