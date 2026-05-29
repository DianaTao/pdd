import json
from pathlib import Path
from pdd.gate_main import run_gate_policy
from pdd.gate_policy import GatePolicy
from pdd.evidence_store import sha256_file

def test_repro_issue_825_allowed(tmp_path: Path):
    project = tmp_path
    code = project / "src" / "refund.py"
    code.parent.mkdir(parents=True)
    code.write_text("def refund():\n    return 1\n", encoding="utf-8")
    
    manifest_path = project / ".pdd" / "evidence" / "devunits" / "refund.latest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
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
    
    policy_file = project / "policy.yml"
    policy_file.write_text(
        "allow:\n  skipped_verify: true\n  skipped_tests: true\n",
        encoding="utf-8",
    )
    
    result = run_gate_policy(project, target="refund", policy_path=policy_file)
    
    print(f"Passed: {result.passed}")
    for failure in result.failures:
        print(f"Failure: {failure.code} - {failure.message}")
    
    assert result.passed, f"Gate should have passed but failed with {result.failures}"

if __name__ == "__main__":
    import sys
    from pathlib import Path
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_repro_issue_825_allowed(Path(tmpdir))
