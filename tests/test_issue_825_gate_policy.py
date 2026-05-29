import json
import pytest
from pathlib import Path
from pdd.gate_main import run_gate_policy
from pdd.evidence_store import sha256_file

def test_issue_825_regression(tmp_path: Path):
    """Verifies that allow.skipped_verify: true and allow.skipped_tests: true 
    correctly allow skipped validations when require.*_pass are true.
    """
    project = tmp_path
    code = project / "src" / "refund.py"
    code.parent.mkdir(parents=True)
    code.write_text("def refund():\n    return 1\n", encoding="utf-8")
    
    manifest_path = project / ".pdd" / "evidence" / "devunits" / "refund.latest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Payload with 'not_applicable' for verify and unit_tests
    payload = {
        "schema_version": 1,
        "run": {"id": "run-refund", "command": "pdd sync", "pdd_version": "0.0.0"},
        "prompt": {"path": "prompts/refund_python.prompt"},
        "outputs": [{"path": "src/refund.py", "sha256": sha256_file(code)}],
        "validation": {
            "detect_stories": "passed",
            "verify": "not_applicable",
            "unit_tests": "not_applicable",
        },
        "generation": {"cost_usd": 1.0},
        "contracts": {},
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    
    # Policy that ALLOWS skipped verify and tests
    policy_file = project / "policy.yml"
    policy_file.write_text(
        "allow:\n  skipped_verify: true\n  skipped_tests: true\n",
        encoding="utf-8",
    )
    
    # By default, require.verify_pass and require.unit_tests_pass are True.
    # The bug was that even with allow.skipped_*, the gate failed if they were not 'passed'.
    result = run_gate_policy(project, target="refund", policy_path=policy_file)
    
    assert result.passed, f"Gate should have passed because skips are allowed. Failures: {result.failures}"

def test_issue_825_regression_fails_when_not_allowed(tmp_path: Path):
    """Verifies that without allow.skipped_*, the gate correctly fails for skipped validations."""
    project = tmp_path
    code = project / "src" / "refund_fail.py"
    code.parent.mkdir(parents=True)
    code.write_text("def refund():\n    return 1\n", encoding="utf-8")
    
    manifest_path = project / ".pdd" / "evidence" / "devunits" / "refund_fail.latest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    payload = {
        "schema_version": 1,
        "run": {"id": "run-refund", "command": "pdd sync", "pdd_version": "0.0.0"},
        "prompt": {"path": "prompts/refund_python.prompt"},
        "outputs": [{"path": "src/refund_fail.py", "sha256": sha256_file(code)}],
        "validation": {
            "detect_stories": "passed",
            "verify": "not_applicable",
            "unit_tests": "not_applicable",
        },
        "generation": {"cost_usd": 1.0},
        "contracts": {},
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    
    # Policy that DOES NOT allow skipped verify and tests (default is false)
    policy_file = project / "policy_strict.yml"
    policy_file.write_text(
        "require:\n  verify_pass: true\n  unit_tests_pass: true\n",
        encoding="utf-8",
    )
    
    result = run_gate_policy(project, target="refund_fail", policy_path=policy_file)
    
    assert not result.passed, "Gate should have failed because skips are not allowed by default."
    failure_codes = [f.code for f in result.failures]
    assert "verify_pass" in failure_codes or "skipped_verify" in failure_codes
    assert "unit_tests_pass" in failure_codes or "skipped_tests" in failure_codes
