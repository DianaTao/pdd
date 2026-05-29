import json
import os
from pathlib import Path
import pytest
from click.testing import CliRunner
from pdd.cli import cli
from pdd.evidence_store import sha256_file
from unittest.mock import patch, MagicMock

def test_gate_cli_allowed_skip_e2e(tmp_path: Path):
    """
    E2E test for Issue #825.
    Verifies that 'pdd checkup gate' correctly respects 'allow.skipped_verify' 
    and 'allow.skipped_tests' in the policy when manifests have 'not_applicable'.
    """
    project = tmp_path
    # Create a dummy source file
    code = project / "src" / "dummy.py"
    code.parent.mkdir(parents=True)
    code.write_text("def dummy(): pass\n")
    
    # Create a dummy prompt file
    prompt_dir = project / "prompts"
    prompt_dir.mkdir()
    prompt_file = prompt_dir / "dummy.prompt"
    prompt_file.write_text("Instruction: do dummy\n")
    
    # Create an evidence manifest with skipped validation
    evidence_dir = project / ".pdd" / "evidence" / "devunits"
    evidence_dir.mkdir(parents=True)
    manifest_path = evidence_dir / "dummy.latest.json"
    
    manifest_data = {
        "schema_version": 1,
        "run": {"id": "test-run", "command": "pdd sync", "pdd_version": "0.0.0"},
        "prompt": {"path": "prompts/dummy.prompt"},
        "outputs": [{"path": "src/dummy.py", "sha256": sha256_file(code)}],
        "validation": {
            "detect_stories": "passed",
            "verify": "not_applicable",
            "unit_tests": "not_applicable",
        },
        "generation": {"cost_usd": 0.1},
    }
    manifest_path.write_text(json.dumps(manifest_data))
    
    # Create a policy that ALLOWS skips
    policy_path = project / "policy.yml"
    policy_path.write_text("allow:\n  skipped_verify: true\n  skipped_tests: true\n")
    
    runner = CliRunner()
    os.chdir(project)
    
    # 1. Test with policy that ALLOWS skips
    result = runner.invoke(cli, ["checkup", "gate", "--policy", str(policy_path)])
    if result.exit_code != 0:
        print(f"STDOUT: {result.output}")
    assert result.exit_code == 0
    assert "PDD gate passed" in result.output
    
    # 2. Test with default policy (which SHOULD FAIL if it requires them)
    # Default policy usually requires verify_pass and unit_tests_pass
    result_default = runner.invoke(cli, ["checkup", "gate"])
    assert result_default.exit_code != 0
    assert "PDD gate failed" in result_default.output

def test_gate_cli_dir_propagation_e2e(tmp_path: Path):
    """
    Integration test for interface consistency.
    Verifies that --stories-dir and --tests-dir options are correctly passed 
    from CLI to run_gate_policy.
    """
    project = tmp_path
    stories_dir = project / "custom_stories"
    stories_dir.mkdir()
    tests_dir = project / "custom_tests"
    tests_dir.mkdir()
    
    os.chdir(project)
    
    # We mock run_gate_policy to verify the arguments it receives
    with patch("pdd.commands.gate.run_gate_policy") as mock_run:
        # Setup mock to return a passing result
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.manifests_checked = 0
        mock_result.exit_code = 0
        mock_run.return_value = mock_result
        
        runner = CliRunner()
        result = runner.invoke(cli, [
            "checkup", "gate", 
            "--stories-dir", str(stories_dir),
            "--tests-dir", str(tests_dir)
        ])
        
        assert result.exit_code == 0
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        
        # kwargs['stories_dir'] should be a Path object pointing to stories_dir
        assert kwargs["stories_dir"] == stories_dir
        assert kwargs["tests_dir"] == tests_dir

def test_full_import_chain_e2e():
    """
    Integration test for Fix 3: Import order.
    Ensures the CLI can be invoked without E402-related crashes or initialization issues.
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "[OPTIONS] COMMAND [ARGS]..." in result.output
    assert "checkup" in result.output
