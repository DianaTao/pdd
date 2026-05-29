"""Smoke tests for the checkup gate demo example and fixtures."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from examples.checkup_gate_demo.manifests import write_demo_manifest
from pdd.evidence_store import sha256_file
from pdd.gate_main import run_gate_policy

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "examples" / "checkup_gate_demo"
EXAMPLE_SCRIPT = REPO_ROOT / "examples" / "checkup_gate_example.py"


def test_fixture_tree_exists() -> None:
    assert (FIXTURE_ROOT / "prompts" / "refund_python.prompt").is_file()
    assert (FIXTURE_ROOT / "agent.prompt").is_file()
    assert (FIXTURE_ROOT / ".pdd" / "policy-permissive.yml").is_file()
    tracked = subprocess.run(
        ["git", "ls-files", "--", "examples/checkup_gate_demo/src/refund.py"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert tracked.returncode == 0
    assert not tracked.stdout.strip(), "src/refund.py must not be committed (PDD-generated)"


def test_demo_manifest_writer_roundtrip(tmp_path: Path) -> None:
    code = tmp_path / "src" / "refund.py"
    code.parent.mkdir(parents=True)
    code.write_text("def refund():\n    return 1\n", encoding="utf-8")
    manifest = tmp_path / ".pdd" / "evidence" / "devunits" / "refund.latest.json"
    write_demo_manifest(
        manifest,
        basename="refund",
        output_rel="src/refund.py",
        output_hash=sha256_file(code),
        validation={"detect_stories": "pass", "verify": "pass", "unit_tests": "pass"},
    )
    result = run_gate_policy(tmp_path, target="refund")
    assert result.passed


def test_checkup_gate_example_script_runs() -> None:
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE_SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "All offline scenarios passed." in completed.stdout


def test_gate_refund_ignores_stories_devunit_manifest(tmp_path: Path) -> None:
    """``pdd detect --stories --evidence`` updates ``stories.latest.json``, not ``refund``."""
    code = tmp_path / "src" / "refund.py"
    code.parent.mkdir(parents=True)
    code.write_text("def refund():\n    return 1\n", encoding="utf-8")
    devunits = tmp_path / ".pdd" / "evidence" / "devunits"
    write_demo_manifest(
        devunits / "refund.latest.json",
        basename="refund",
        output_rel="src/refund.py",
        output_hash=sha256_file(code),
        validation={
            "detect_stories": "not_applicable",
            "unit_tests": "failed",
            "verify": "not_available",
        },
    )
    write_demo_manifest(
        devunits / "stories.latest.json",
        basename="stories",
        output_rel="src/refund.py",
        output_hash=sha256_file(code),
        validation={
            "detect_stories": "passed",
            "unit_tests": "not_available",
            "verify": "not_available",
        },
    )
    result = run_gate_policy(tmp_path, target="refund")
    assert not result.passed
    codes = {failure.code for failure in result.failures}
    assert "stories_pass" in codes
    assert "unit_tests_pass" in codes


def test_demo_failed_sync_gate_script_runs() -> None:
    script = FIXTURE_ROOT / "demo_failed_sync_gate.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=FIXTURE_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **dict(__import__("os").environ),
            "PDD_SKIP_UPDATE_CHECK": "1",
            "CI": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert '"passed": false' in completed.stdout
    assert "stories_pass" in completed.stdout


@pytest.mark.parametrize(
    "script_name",
    ["run_offline_checks.sh", "run_cli_smoke.sh"],
)
def test_demo_shell_scripts_are_executable(script_name: str) -> None:
    path = FIXTURE_ROOT / script_name
    assert path.is_file()
    assert path.stat().st_mode & 0o111
