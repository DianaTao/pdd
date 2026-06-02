
import os
import json
import pytest
import asyncio
from pathlib import Path
from click.testing import CliRunner
from fastapi.testclient import TestClient

from pdd.cli import cli
from pdd.server.app import create_app
from pdd.server.models import ServerConfig
from pdd.edit_file import edit_file

@pytest.fixture
def project_root(tmp_path):
    """Create a mock project root with necessary files."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "pdd").mkdir()
    (tmp_path / "pdd" / "commands").mkdir()
    
    # Create a dummy prompt file
    prompt_file = tmp_path / "prompts" / "test.prompt"
    prompt_file.write_text("Test prompt content")
    
    # Create a dummy architecture.json if needed, but we'll use the real one for some tests
    
    return tmp_path

def test_checkup_simplify_integration(project_root, mocker):
    """Test 'pdd checkup simplify' integration with cost tracking."""
    # Mock the underlying run_checkup_simplify to avoid real LLM calls
    mock_result = mocker.Mock()
    mock_result.summary_lines = ["Simplified 1 file", "Fixed 2 issues"]
    mock_result.cost = 0.05
    mock_result.provider = "test-provider"
    mock_result.exit_code = 0
    
    mocker.patch("pdd.commands.checkup_simplify.run_checkup_simplify", return_value=mock_result)
    
    # Setup cost tracking path
    cost_path = project_root / "cost.csv"
    os.environ["PDD_OUTPUT_COST_PATH"] = str(cost_path)
    
    runner = CliRunner()
    # We need to be in the project root for some commands
    with runner.isolated_filesystem(temp_dir=project_root):
        # Create the prompt file in the isolated filesystem
        Path("prompts").mkdir(exist_ok=True)
        (Path("prompts") / "test.prompt").write_text("test")
        
        # Temporarily unset PYTEST_CURRENT_TEST to allow @track_cost to write
        orig_pytest_env = os.environ.get("PYTEST_CURRENT_TEST")
        if orig_pytest_env:
            del os.environ["PYTEST_CURRENT_TEST"]
        
        try:
            result = runner.invoke(cli, ["checkup", "simplify", "--engine", "auto"])
            assert result.exit_code == 0
            assert "Simplified 1 file" in result.output
            
            # Verify cost tracking
            assert cost_path.exists()
            content = cost_path.read_text()
            assert "test-provider" in content
            assert "0.05" in content
            assert "simplify" in content
        finally:
            if orig_pytest_env:
                os.environ["PYTEST_CURRENT_TEST"] = orig_pytest_env

def test_prompts_analyze_integration(project_root):
    """Test FastAPI /prompts/analyze integration with Pydantic models."""
    app = create_app(project_root)
    client = TestClient(app)
    
    # Create a prompt file for analysis
    prompt_path = "prompts/test.prompt"
    (project_root / prompt_path).write_text("Hello {{ name }}")
    
    response = client.post(
        "/api/v1/prompts/analyze",
        json={
            "path": prompt_path,
            "model": "claude-3-5-sonnet-20240620",
            "preprocess": True
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "raw_metrics" in data
    assert "token_count" in data["raw_metrics"]
    # Verify the structure matches our fixed Pydantic models
    if data["raw_metrics"].get("cost_estimate"):
        assert "input_cost" in data["raw_metrics"]["cost_estimate"]
        assert "model" in data["raw_metrics"]["cost_estimate"]

def test_app_creation_with_config(project_root):
    """Test create_app handles ServerConfig correctly."""
    config = ServerConfig(
        host="0.0.0.0",
        port=1234,
        log_level="debug"
    )
    app = create_app(project_root, config=config)
    
    client = TestClient(app)
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    # The AppState should have the config
    from pdd.server.app import get_app_state
    state = get_app_state()
    assert state.config.port == 1234
    assert state.config.host == "0.0.0.0"

@pytest.mark.asyncio
async def test_edit_file_integration(tmp_path):
    """Test edit_file integration and its robustness wrapper."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Original content")
    
    # Even if langgraph is missing, it should return a graceful error
    # instead of crashing on import.
    success, error = await edit_file(str(test_file), "change content to 'New content'")
    
    from pdd.edit_file import HAS_LANGGRAPH
    if not HAS_LANGGRAPH:
        assert success is False
        assert "requires langgraph" in error
    else:
        # If it IS present, it might still fail if no API key is set, 
        # but we've verified it doesn't crash on import.
        pass

def test_architecture_json_usage():
    """Verify architecture.json integrity and path resolution."""
    arch_path = Path("architecture.json")
    assert arch_path.exists()
    
    with open(arch_path, 'r') as f:
        data = json.load(f)
    
    # Verify that the fixed paths exist in the repo
    paths_to_check = [
        "tests/prompt_tester.py",
        "utils/run_generated.py",
        "prompts/regression_bash.prompt",
        "pdd/edit_file.py"
    ]
    
    for p in paths_to_check:
        assert Path(p).exists(), f"Path {p} from architecture.json does not exist"

    # Verify step numbers were updated
    content_str = json.dumps(data)
    # Based on step6a: reproduction moved from Step 4 to Step 5
    # We check for the presence of the new step names
    assert "step5_reproduction" in content_str or "step 5" in content_str.lower()
