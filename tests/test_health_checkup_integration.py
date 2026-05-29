import json
from pathlib import Path
from click.testing import CliRunner
from pdd.cli import cli as main
from pdd.evidence_store import sha256_file
import pytest

@pytest.fixture
def runner():
    return CliRunner()

def test_gate_cli_integration_success(runner, tmp_path: Path):
    """E2E test: pdd gate passes when skips are allowed by policy."""
    project = tmp_path
    # pdd gate expects to run from project root
    with runner.isolated_filesystem(temp_dir=project):
        # Setup dummy code and manifest
        code = Path("src/gate_success.py")
        code.parent.mkdir(parents=True)
        code.write_text("def success(): pass\n", encoding="utf-8")
        
        manifest_dir = Path(".pdd/evidence/devunits")
        manifest_dir.mkdir(parents=True)
        manifest_path = manifest_dir / "gate_success.latest.json"
        
        payload = {
            "schema_version": 1,
            "run": {"id": "run-success", "command": "pdd sync", "pdd_version": "0.0.0"},
            "prompt": {"path": "prompts/test_python.prompt"},
            "outputs": [{"path": str(code), "sha256": sha256_file(code)}],
            "validation": {
                "detect_stories": "passed",
                "verify": "skipped",
                "unit_tests": "not_applicable",
            },
            "generation": {"cost_usd": 0.05},
            "contracts": {},
        }
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        
        # Setup policy
        policy_path = Path("policy_allow.yml")
        policy_path.write_text(
            "allow:\n  skipped_verify: true\n  skipped_tests: true\n",
            encoding="utf-8"
        )
        
        # Run pdd gate
        result = runner.invoke(main, ["checkup", "gate", "gate_success", "--policy", str(policy_path)])
        
        assert result.exit_code == 0
        assert "PDD gate passed" in result.output
        assert "1 manifest(s) checked" in result.output

def test_gate_cli_integration_failure(runner, tmp_path: Path):
    """E2E test: pdd gate fails when skips are NOT allowed by policy."""
    project = tmp_path
    with runner.isolated_filesystem(temp_dir=project):
        # Setup dummy code and manifest
        code = Path("src/gate_fail.py")
        code.parent.mkdir(parents=True)
        code.write_text("def fail(): pass\n", encoding="utf-8")
        
        manifest_dir = Path(".pdd/evidence/devunits")
        manifest_dir.mkdir(parents=True)
        manifest_path = manifest_dir / "gate_fail.latest.json"
        
        payload = {
            "schema_version": 1,
            "run": {"id": "run-fail", "command": "pdd sync", "pdd_version": "0.0.0"},
            "prompt": {"path": "prompts/test_python.prompt"},
            "outputs": [{"path": str(code), "sha256": sha256_file(code)}],
            "validation": {
                "detect_stories": "passed",
                "verify": "skipped",
                "unit_tests": "not_applicable",
            },
            "generation": {"cost_usd": 0.05},
            "contracts": {},
        }
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        
        # Setup strict policy
        policy_path = Path("policy_strict.yml")
        policy_path.write_text(
            "require:\n  verify_pass: true\n  unit_tests_pass: true\n",
            encoding="utf-8"
        )
        
        # Run pdd gate
        result = runner.invoke(main, ["checkup", "gate", "gate_fail", "--policy", str(policy_path)])
        
        assert result.exit_code == 1
        assert "PDD gate failed" in result.output
        assert "verify was skipped against policy" in result.output
        assert "unit tests were skipped against policy" in result.output

def test_gate_cli_json_output(runner, tmp_path: Path):
    """Integration test: pdd gate --json output format."""
    project = tmp_path
    with runner.isolated_filesystem(temp_dir=project):
        code = Path("src/gate_json.py")
        code.parent.mkdir(parents=True)
        code.write_text("def json_test(): pass\n", encoding="utf-8")
        
        manifest_dir = Path(".pdd/evidence/devunits")
        manifest_dir.mkdir(parents=True)
        manifest_path = manifest_dir / "gate_json.latest.json"
        
        payload = {
            "schema_version": 1,
            "run": {"id": "run-json", "command": "pdd sync", "pdd_version": "0.0.0"},
            "prompt": {"path": "prompts/test_python.prompt"},
            "outputs": [{"path": str(code), "sha256": sha256_file(code)}],
            "validation": {"detect_stories": "passed", "verify": "passed", "unit_tests": "passed"},
            "generation": {"cost_usd": 0.0},
            "contracts": {},
        }
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        
        result = runner.invoke(main, ["--no-core-dump", "--quiet", "checkup", "gate", "gate_json", "--json"])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["passed"] is True
        assert data["manifests_checked"] == 1
        assert "policy" in data

def test_agentic_common_integration_flow():
    """Integration test: verify extract_step_report works in a realistic orchestrator context."""
    from pdd.agentic_common import extract_step_report
    
    llm_output = (
        "Analysis of the issue:\n"
        "The bug is in the parser.\n\n"
        "Plan:\n"
        "1. Fix the parser.\n"
        "2. Add tests.\n\n"
        "<step_report>\n"
        "## Step 3/8: Parser Fix\n\n"
        "I have fixed the parser by updating the regex in `pdd/parser.py`.\n"
        "Verification: `pytest tests/test_parser.py` passed.\n"
        "</step_report>\n\n"
        "Conclusion: The fix is ready for review."
    )
    
    report = extract_step_report(llm_output)
    assert report is not None
    assert "## Step 3/8: Parser Fix" in report
    assert "I have fixed the parser" in report
    assert "Conclusion" not in report
    assert "Analysis" not in report

def test_agentic_common_export_access():
    """Integration test: verify that the fixed module exports are accessible via high-level imports."""
    import pdd.agentic_common
    assert hasattr(pdd.agentic_common, "extract_step_report")
    assert callable(pdd.agentic_common.extract_step_report)
    
    # Verify we can also import it directly
    from pdd.agentic_common import extract_step_report
    assert extract_step_report("<step_report>TEST</step_report>") == "TEST"
