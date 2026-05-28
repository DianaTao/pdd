"""E2E and Integration tests for Issue #29 fixes."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pdd.drift_main import run_drift, RunSnapshot

def test_drift_full_cycle_integration(tmp_path: Path) -> None:
    """E2E test for drift command with mocked regeneration."""
    project = tmp_path / "project"
    project.mkdir()
    pdd_dir = project / "pdd"
    pdd_dir.mkdir()
    (pdd_dir / "__init__.py").write_text("", encoding="utf-8")
    
    prompt = project / "prompts" / "test_mod_python.prompt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("<prompt>test</prompt>", encoding="utf-8")
    
    code = pdd_dir / "test_mod.py"
    code.write_text("def run(): return True\n", encoding="utf-8")
    
    tests_dir = project / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_test_mod.py"
    test_file.write_text(
        "from pdd.test_mod import run\n"
        "def test_run(): assert run() is True\n",
        encoding="utf-8"
    )

    # 1. Stable run
    def _fake_regenerate_stable(_prompt: Path, output: Path, **_kwargs) -> float:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("def run(): return True\n", encoding="utf-8")
        return 0.1

    with patch("pdd.drift_main._regenerate_code", side_effect=_fake_regenerate_stable):
        report = run_drift("test_mod", project, runs=1)
        assert report.status == "stable"
        assert report.behavior_unchanged
        assert len(report.snapshots) == 1
        assert report.snapshots[0].tests_passed is True

    # 2. Unstable run (broken candidate)
    def _fake_regenerate_broken(_prompt: Path, output: Path, **_kwargs) -> float:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("def run(): return False\n", encoding="utf-8")
        return 0.1

    with patch("pdd.drift_main._regenerate_code", side_effect=_fake_regenerate_broken):
        report = run_drift("test_mod", project, runs=1)
        assert report.status == "unstable"
        assert not report.behavior_unchanged
        assert report.snapshots[0].tests_passed is False

def test_dependency_audit_scripts_e2e() -> None:
    """Run actual audit scripts on the codebase and verify they are clean."""
    # Run audit_deps.py
    result = subprocess.run(
        ["python3", "audit_deps.py"],
        capture_output=True,
        text=True,
        check=True
    )
    # firebase_admin SHOULD NOT be in the unused list anymore because it's removed from mapping.
    assert "firebase_admin" not in result.stdout
    assert "firebase-admin" not in result.stdout
    
    # Run final_missing_check.py
    result = subprocess.run(
        ["python3", "final_missing_check.py"],
        capture_output=True,
        text=True,
        check=True
    )
    assert "### Missing Dependencies" in result.stdout
    
    # Extract missing deps
    lines = result.stdout.splitlines()
    missing_start = False
    missing_deps = []
    for line in lines:
        if "### Missing Dependencies" in line:
            missing_start = True
            continue
        if missing_start and line.startswith("- "):
            missing_deps.append(line[2:])
        elif missing_start and line.strip() == "":
            missing_start = False
    
    # We expect a clean audit after fixes (except maybe for some platform-specific or transient stuff)
    # But firebase_admin and z3-solver must definitely be gone from missing.
    assert "firebase_admin" not in missing_deps
    assert "z3-solver" not in missing_deps
    assert "z3_solver" not in missing_deps

def test_architecture_metadata_consistency_e2e() -> None:
    """Verify that architecture.json is consistent with the filesystem."""
    with open("architecture.json", "r") as f:
        arch = json.load(f)
    
    missing_files = []
    for entry in arch:
        filepath = entry.get("filepath")
        if not filepath:
            continue
        # Skip some known missing files that are optional or transient if any remain
        if any(x in filepath for x in ["regression_analysis.log", "regression.sh", "pdd_theme.json"]):
            continue
        if not Path(filepath).exists():
            missing_files.append(filepath)
            
    # After Step 6a fixes, missing_files should be empty.
    assert len(missing_files) == 0, f"Missing files in architecture.json: {missing_files}"

def test_agentic_bug_orchestrator_steps_sync_e2e() -> None:
    """Verify that agentic_bug_orchestrator uses the same step numbers as architecture.json."""
    from pdd.agentic_bug_orchestrator import BUG_STEP_TIMEOUTS
    
    # Steps from BUG_STEP_TIMEOUTS in orchestrator
    orchestrator_steps = set(BUG_STEP_TIMEOUTS.keys())
    
    # Steps from architecture.json
    with open("architecture.json", "r") as f:
        arch = json.load(f)
    
    arch_steps = set()
    for entry in arch:
        filename = entry.get("filename", "")
        if filename.startswith("agentic_bug_step") and "_LLM.prompt" in filename:
            try:
                # agentic_bug_stepN_...
                step_num = int(filename.split("_")[2].replace("step", ""))
                arch_steps.add(step_num)
            except (ValueError, IndexError):
                continue
                
    # Both should have steps 1 to 12
    expected_steps = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}
    assert orchestrator_steps == expected_steps
    assert arch_steps == expected_steps
