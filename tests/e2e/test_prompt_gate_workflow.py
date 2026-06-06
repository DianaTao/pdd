"""End-to-end prompt-gate workflow tests for PR #1428 (#1420).

These drive the **real** ``pdd checkup`` / ``pdd change`` / ``pdd generate`` CLIs in
real subprocesses against disposable fixture projects, stubbing only the model /
provider boundary (see ``tests/e2e/_fake_provider_cli.py``). The prompt gate,
``change_main``, gate-mode resolution from ``.pddrc`` and the source-set report all
run for real — so the asserted exit codes are genuine process results from the gate.

Reviewers can run just these::

    pytest -vv tests/e2e/test_prompt_gate_workflow.py

or print a human-readable transcript with::

    python scripts/prompt_gate_e2e_demo.py

The scenario runners live in ``scripts/prompt_gate_e2e_demo.py`` (single source of
truth, also runnable standalone); this module imports them and asserts.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_PATH = REPO_ROOT / "scripts" / "prompt_gate_e2e_demo.py"

# Import the standalone demo module by path (scripts/ is not an importable package).
# Register it in sys.modules before exec so @dataclass can resolve its module.
_spec = importlib.util.spec_from_file_location("prompt_gate_e2e_demo", _DEMO_PATH)
assert _spec and _spec.loader
demo = importlib.util.module_from_spec(_spec)
sys.modules["prompt_gate_e2e_demo"] = demo
_spec.loader.exec_module(demo)

pytestmark = pytest.mark.slow  # subprocess-based; deterministic, no real LLM calls.


def test_checkup_prompt_json_schema_real_cli(tmp_path: Path) -> None:
    res = demo.run_checkup_clean(tmp_path)
    assert res.exit_code in {0, 1}, res.stderr
    payload = json.loads(res.stdout)
    assert payload["schema"] == "pdd.prompt_source_set_report.v1"
    assert payload["reports"], "expected at least one per-prompt report"
    report = payload["reports"][0]
    assert {"checks", "findings", "status"} <= set(report)
    # The unified report runs the deterministic source-set engines.
    check_names = {check["name"] for check in report["checks"]}
    assert {"lint", "contract", "coverage"} <= check_names


def test_checkup_nested_project_root_anchors_coverage(tmp_path: Path) -> None:
    """The #1428 rooting fix, validated through a real user-style CLI invocation.

    The prompt and its covering story live under a nested project; checkup is run
    from an external cwd with ``--project-root``. Coverage must resolve against the
    project root (story found ⇒ rules 'story-only', zero 'unchecked'), not the cwd.
    """
    res = demo.run_checkup_nested(tmp_path)
    assert res.exit_code in {0, 1}, res.stderr
    unchecked = demo._coverage_unchecked_count(res.stdout)
    assert unchecked == 0, (
        "coverage rules reported as 'unchecked' from an external cwd — the project-"
        f"root anchoring regressed. stdout=\n{res.stdout}"
    )


def test_change_manual_warn_gate_reports_and_continues(tmp_path: Path) -> None:
    res = demo.run_change_manual(tmp_path, gate_mode="warn", cli_flag=None)
    assert res.exit_code == 0, res.stderr
    # Prompt written first, then the real gate ran and reported findings.
    assert "saved to" in res.stdout
    assert "Prompt checkup: needs attention" in res.stdout


def test_change_manual_strict_gate_blocks_nonzero(tmp_path: Path) -> None:
    res = demo.run_change_manual(tmp_path, gate_mode="warn", cli_flag="strict")
    assert res.exit_code == 2, res.stderr
    assert "saved to" in res.stdout  # the prompt write happened before the gate
    assert "Prompt checkup blocked" in res.stdout


def test_change_manual_off_via_unquoted_pddrc_skips_gate(tmp_path: Path) -> None:
    """Unquoted ``prompt_gate: off`` (PyYAML boolean False) disables the gate."""
    res = demo.run_change_manual(tmp_path, gate_mode="off", cli_flag=None)
    assert res.exit_code == 0, res.stderr
    assert "saved to" in res.stdout
    assert "Prompt checkup" not in res.stdout  # gate skipped entirely


def test_generate_agentic_warn_gate_reports_and_continues(tmp_path: Path) -> None:
    res = demo.run_generate_agentic(tmp_path, gate_mode="warn", cli_flag="warn")
    assert res.exit_code == 0, res.stderr
    assert "Prompt checkup: needs attention" in res.stdout


def test_generate_agentic_strict_via_pddrc_blocks_nonzero(tmp_path: Path) -> None:
    res = demo.run_generate_agentic(tmp_path, gate_mode="strict", cli_flag=None)
    assert res.exit_code == 2, res.stderr
    assert "Prompt checkup" in res.stdout
