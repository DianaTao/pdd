
import pytest
import os
import json
from pathlib import Path
from click.testing import CliRunner
from pdd.cli import cli

@pytest.fixture
def project_root(tmp_path):
    # Setup a minimal project structure
    (tmp_path / "prompts").mkdir()
    (tmp_path / "pdd").mkdir()
    (tmp_path / ".pdd").mkdir()
    
    # Create a dummy pddrc
    pddrc = tmp_path / ".pddrc"
    pddrc.write_text(json.dumps({
        "project_name": "test-project",
        "language": "python",
        "contexts": {
            "default": {
                "defaults": {
                    "generate_output_path": "pdd/"
                }
            }
        }
    }))
    
    # Change to project root for the duration of the test
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)

def test_pdd_connect_cli_e2e(project_root, mocker):
    """E2E: Test 'pdd connect' starts the server and handles config."""
    # Mock run_server to avoid actual uvicorn execution
    mock_run_server = mocker.patch("uvicorn.run")
    # Mock port availability to be predictable
    mocker.patch("pdd.commands.connect.is_port_available", return_value=True)
    mocker.patch("pdd.commands.connect.find_available_port", return_value=9999)
    
    runner = CliRunner()
    # Use --no-browser and --local-only to avoid side effects in tests
    result = runner.invoke(cli, ["connect", "--port", "9999", "--host", "0.0.0.0", "--no-browser", "--local-only"])
    
    assert result.exit_code == 0
    # Verify uvicorn.run was called with correct port and host
    assert mock_run_server.called
    _, kwargs = mock_run_server.call_args
    assert kwargs["port"] == 9999
    assert kwargs["host"] == "0.0.0.0"

def test_pdd_sync_dry_run_e2e(project_root, mocker):
    """E2E: Test 'pdd sync --dry-run' integration with file discovery."""
    # Mock the core sync logic to avoid real LLM calls
    mocker.patch("pdd.sync_main.sync_main", return_value=0)
    
    runner = CliRunner()
    
    # Create a prompt file
    prompt_file = project_root / "prompts" / "test_python.prompt"
    prompt_file.write_text("Test prompt")
    
    result = runner.invoke(cli, ["sync", "test", "--dry-run"])
    
    assert result.exit_code == 0
    # The output should indicate it's a dry run
    assert "dry run" in result.output.lower() or "would" in result.output.lower()

def test_pdd_sync_architecture_e2e(project_root, mocker):
    """E2E: Test 'pdd sync-architecture' integration."""
    # Mock the architecture sync logic helper
    mocker.patch("pdd.commands.maintenance.sync_prompts_to_architecture", return_value={
        "success": True,
        "updated_count": 0,
        "skipped_count": 0,
        "results": [],
        "validation": {"valid": True, "errors": [], "warnings": []},
        "errors": []
    })
    
    runner = CliRunner()
    result = runner.invoke(cli, ["sync-architecture"])
    
    assert result.exit_code == 0
