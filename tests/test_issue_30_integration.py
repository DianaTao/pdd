"""
Integration and E2E tests for Issue #30 fixes.
Verifies candidate isolation, policy gating behavior, and cross-module interactions.
"""
import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

from pdd.drift_main import run_drift
from pdd.evidence_store import sha256_file
from pdd.agentic_langtest import default_verify_cmd_for

def _write_complex_fixture(project: Path) -> tuple[Path, Path, Path]:
    """
    Project with a package 'pdd', a module 'calculator', 
    and a test 'tests/test_calculator.py'.
    """
    pdd_dir = project / "pdd"
    pdd_dir.mkdir(parents=True, exist_ok=True)
    (pdd_dir / "__init__.py").write_text("", encoding="utf-8")
    
    code_path = pdd_dir / "calculator.py"
    code_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    
    prompt_dir = project / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / "calculator.prompt"
    prompt_path.write_text("<prompt>\nCalculator module.\n</prompt>\n", encoding="utf-8")
    
    test_dir = project / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / "test_calculator.py"
    test_path.write_text(
        "from pdd.calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8"
    )
    
    return prompt_path, code_path, test_path

def test_drift_e2e_isolation_with_real_pytest(tmp_path: Path):
    """
    End-to-end test: verify that run_drift correctly isolates the candidate
    from the baseline using a real pytest invocation.
    
    The baseline (on disk) is GOOD (2+3=5).
    The candidate (injected) is BROKEN (returns 0).
    If isolation works, the test must FAIL for the candidate.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prompt_path, _code_path, _test_path = _write_complex_fixture(project_root)
    
    # 2. Mock regeneration to return a BROKEN candidate
    def _fake_regenerate(p_path, out_path, **kwargs):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
        return 0.01

    with patch("pdd.drift_main._regenerate_code", side_effect=_fake_regenerate):
        # We don't mock _evaluate_candidate, we want it to run for real
        # This will call _run_pytest_for_candidate which uses subprocess.run([sys.executable, -m pytest])
        report = run_drift("calculator", project_root, runs=1, dry_run=False)

    # 3. Verify: It should be UNSTABLE because the candidate fails the test
    assert report.status == "unstable"
    assert not report.behavior_unchanged
    assert len(report.snapshots) == 1
    assert report.snapshots[0].tests_passed is False

def test_drift_e2e_isolation_opposite_case(tmp_path: Path):
    """
    Verify the opposite: Baseline is BROKEN, Candidate is GOOD.
    If isolation works, the test must PASS for the candidate.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prompt_path, code_path, _test_path = _write_complex_fixture(project_root)
    
    # Make baseline BROKEN
    code_path.write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
    
    # Mock regeneration to return a GOOD candidate
    def _fake_regenerate(p_path, out_path, **kwargs):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return 0.01

    with patch("pdd.drift_main._regenerate_code", side_effect=_fake_regenerate):
        report = run_drift("calculator", project_root, runs=1, dry_run=False)

    # 3. Verify: It should be STABLE because the candidate passes the test
    # despite the baseline on disk being broken.
    assert report.status == "stable"
    assert report.behavior_unchanged
    assert len(report.snapshots) == 1
    assert report.snapshots[0].tests_passed is True

def test_drift_e2e_policy_fail_open_gate_missing(tmp_path: Path):
    """
    Verify that if a policy is configured but the gate tool is missing,
    the drift run still passes (fail-open).
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prompt_path, _code_path, _test_path = _write_complex_fixture(project_root)
    
    # Configure a policy
    policy_file = project_root / ".pdd" / "policy.yml"
    policy_file.parent.mkdir(parents=True)
    policy_file.write_text("rules: []\n", encoding="utf-8")
    
    # Mock regeneration to return a GOOD candidate
    def _fake_regenerate(p_path, out_path, **kwargs):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return 0.01

    with patch("pdd.drift_main._GATE_POLICY_AVAILABLE", False):
        with patch("pdd.drift_main._regenerate_code", side_effect=_fake_regenerate):
            report = run_drift("calculator", project_root, runs=1, dry_run=False)

    assert report.status == "stable"
    assert report.policy_check_unavailable
    assert report.snapshots[0].policy_passed is True

def test_drift_e2e_evidence_no_policy_no_gate_trigger(tmp_path: Path):
    """
    Verify that evidence-backed drift without policy does NOT trigger policy gates.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    prompt_path, code_path, _ = _write_complex_fixture(project_root)
    
    # Create manifest
    manifest_path = project_root / "manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": 1,
        "prompt": {"path": str(prompt_path.relative_to(project_root))},
        "outputs": [{"path": str(code_path.relative_to(project_root)), "sha256": sha256_file(code_path)}],
        "validation": {
            "detect_stories": "not_available",
            "verify": "not_available",
            "unit_tests": "pass"
        }
    }), encoding="utf-8")

    # Mock _run_gate_policy_impl to ensure it's NOT called
    with patch("pdd.drift_main._GATE_POLICY_AVAILABLE", True):
        with patch("pdd.drift_main._run_gate_policy_impl") as mock_gate:
            report = run_drift(
                "calculator", 
                project_root, 
                runs=1, 
                dry_run=True, 
                from_evidence=manifest_path
            )
            
    assert report.status == "stable"
    assert report.policy_check_skipped
    mock_gate.assert_not_called()

def test_agentic_langtest_integration_uses_correct_executable():
    """
    Verify that default_verify_cmd_for returns a command string using sys.executable.
    This is an integration test as it verifies the behavior of the module's 
    main interface after the fix.
    """
    import sys
    # Mock CSV to ensure fallback to hardcoded Python path
    with patch("pdd.agentic_langtest._load_language_format_by_name", return_value={}):
        cmd = default_verify_cmd_for("python", "some_test.py")
    
    assert cmd is not None
    assert cmd.startswith(sys.executable)
    assert "-m pytest" in cmd
    assert "some_test.py" in cmd
