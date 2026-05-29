import json
import pytest
import os
from pathlib import Path
from pdd.gate_main import run_gate_policy
from pdd.evidence_store import sha256_file
from pdd.agentic_common import extract_step_report

def test_gate_policy_skips_allowed_regression(tmp_path: Path):
    """Verifies that allow.skipped_verify and allow.skipped_tests correctly satisfy policy.
    Regression for Issue #825.
    """
    project = tmp_path
    code = project / "src" / "gate_test.py"
    code.parent.mkdir(parents=True)
    code.write_text("def test(): pass\n", encoding="utf-8")
    
    # Test multiple skip-shaped statuses: 'not_applicable', 'skip', 'skipped'
    for status in ["not_applicable", "skip", "skipped"]:
        manifest_path = project / ".pdd" / "evidence" / "devunits" / f"gate_{status}.latest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        payload = {
            "schema_version": 1,
            "run": {"id": f"run-{status}", "command": "pdd sync", "pdd_version": "0.0.0"},
            "prompt": {"path": "prompts/test_python.prompt"},
            "outputs": [{"path": "src/gate_test.py", "sha256": sha256_file(code)}],
            "validation": {
                "detect_stories": "passed",
                "verify": status,
                "unit_tests": status,
            },
            "generation": {"cost_usd": 0.01},
            "contracts": {},
        }
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        
        # Policy that ALLOWS skipped verify and tests
        policy_file = project / f"policy_{status}.yml"
        policy_file.write_text(
            "allow:\n  skipped_verify: true\n  skipped_tests: true\n",
            encoding="utf-8",
        )
        
        result = run_gate_policy(project, target=f"gate_{status}", policy_path=policy_file)
        assert result.passed, f"Gate should have passed for status {status} because skips are allowed. Failures: {result.failures}"

def test_gate_policy_skips_denied_regression(tmp_path: Path):
    """Verifies that without allow.skipped_*, the gate correctly fails for skipped validations."""
    project = tmp_path
    code = project / "src" / "gate_fail.py"
    code.parent.mkdir(parents=True)
    code.write_text("def test(): pass\n", encoding="utf-8")
    
    manifest_path = project / ".pdd" / "evidence" / "devunits" / "gate_fail.latest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    payload = {
        "schema_version": 1,
        "run": {"id": "run-fail", "command": "pdd sync", "pdd_version": "0.0.0"},
        "prompt": {"path": "prompts/test_python.prompt"},
        "outputs": [{"path": "src/gate_fail.py", "sha256": sha256_file(code)}],
        "validation": {
            "detect_stories": "passed",
            "verify": "skipped",
            "unit_tests": "not_applicable",
        },
        "generation": {"cost_usd": 0.01},
        "contracts": {},
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    
    # Policy that requires them but DOES NOT allow skips (default)
    policy_file = project / "policy_strict.yml"
    policy_file.write_text(
        "require:\n  verify_pass: true\n  unit_tests_pass: true\n",
        encoding="utf-8",
    )
    
    result = run_gate_policy(project, target="gate_fail", policy_path=policy_file)
    assert not result.passed, "Gate should have failed because skips are not allowed."
    failure_codes = [f.code for f in result.failures]
    assert "verify_pass" in failure_codes or "skipped_verify" in failure_codes
    assert "unit_tests_pass" in failure_codes or "skipped_tests" in failure_codes

def test_extract_step_report_export_regression():
    """Verifies that extract_step_report is correctly exported from pdd.agentic_common."""
    from pdd.agentic_common import extract_step_report
    
    text = "Intro\n<step_report>\nMy Report\n</step_report>\nOutro"
    assert extract_step_report(text) == "My Report"
    
    # Check it handles case-insensitivity and DOTALL
    text_complex = "<STEP_REPORT>\nLine 1\nLine 2\n</STEP_REPORT>"
    assert extract_step_report(text_complex) == "Line 1\nLine 2"

def test_redundancy_cleanup_files_deleted_regression():
    """Verifies that redundant files are actually gone."""
    base_dir = Path(__file__).parent.parent
    
    deleted_files = [
        base_dir / "pdd" / "postprocess_0.py",
        base_dir / "prompts" / "postprocess_0_python.prompt",
        base_dir / "tests" / "test_postprocess_0.py"
    ]
    
    for f in deleted_files:
        assert not f.exists(), f"Redundant file still exists: {f}"

def test_postprocess_0_in_postprocess_regression():
    """Verifies that postprocess_0 is now correctly located in pdd.postprocess."""
    from pdd.postprocess import postprocess_0
    
    content = "Code block:\n```python\nprint(123)\n```"
    assert postprocess_0(content, "python") == "print(123)"

def test_architecture_json_sync_regression():
    """Verifies that architecture.json is in sync with the fixes."""
    base_dir = Path(__file__).parent.parent
    arch_path = base_dir / "architecture.json"
    
    with open(arch_path, "r", encoding="utf-8") as f:
        arch = json.load(f)
    
    # Check that extract_step_report is in the interface
    found = False
    for entry in arch:
        interface = entry.get("interface", {})
        if interface.get("type") == "module":
            functions = interface.get("module", {}).get("functions", [])
            for func in functions:
                if func.get("name") == "extract_step_report":
                    found = True
                    break
        if found:
            break
    assert found, "extract_step_report not found in architecture.json"
    
    # Check that postprocess_0_python.prompt is REMOVED
    for entry in arch:
        prompt_name = entry.get("filename", "")
        assert "postprocess_0" not in prompt_name, f"Redundant prompt {prompt_name} still in architecture.json"

def test_agentic_common_prompt_interface_regression():
    """Verifies that private functions are removed from agentic_common_python.prompt interface."""
    base_dir = Path(__file__).parent.parent
    prompt_path = base_dir / "prompts" / "agentic_common_python.prompt"
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Extract pdd-interface block
    import re
    interface_match = re.search(r"<pdd-interface>(.*?)</pdd-interface>", content, re.DOTALL)
    assert interface_match, "pdd-interface block not found in prompt"
    
    interface_json = json.loads(interface_match.group(1))
    functions = interface_json.get("module", {}).get("functions", [])
    func_names = [f.get("name") for f in functions]
    
    assert "extract_step_report" in func_names
    assert "_extract_step_report" not in func_names
    assert "_sanitize_comment_body" not in func_names
