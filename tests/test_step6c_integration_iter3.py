
import pytest
import os
import json
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from pdd.server.app import create_app
from pdd.server.models import ServerConfig, StdoutMessage, StderrMessage
from pdd.architecture_sync_helper import filepath_to_prompt_filename
from pdd.generate_output_paths import generate_output_paths

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
        "tests_dir": "tests"
    }))
    
    return tmp_path

def test_sync_status_endpoint_integration(project_root):
    """Test /api/v1/prompts/sync-status endpoint (Integration)."""
    app = create_app(project_root)
    client = TestClient(app)
    
    # Create prompt and code files in the root to match default expectations
    # (No .pddrc contexts configured in this project_root yet)
    prompt_dir = project_root / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / "calc_python.prompt"
    prompt_file.write_text("Calculate sum")
    
    # By default, pdd looks for code in the project root
    code_file = project_root / "calc.py"
    code_file.write_text("def add(a, b): return a + b")
    
    # 1. Test status when never synced
    response = client.get("/api/v1/prompts/sync-status", params={
        "basename": "calc",
        "language": "python"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "never_synced"
    assert data["prompt_exists"] is True
    assert data["code_exists"] is True

def test_diff_analysis_schema_integration(project_root, mocker):
    """Test /api/v1/prompts/diff-analysis integration with fixed Pydantic models."""
    app = create_app(project_root)
    client = TestClient(app)
    
    # Mock llm_invoke to return a valid response that matches our fixed schema
    mock_llm_result = {
        "result": {
            "overallScore": 90,
            "promptToCodeScore": 95,
            "codeToPromptScore": 85,
            "canRegenerate": True,
            "regenerationRisk": "low",
            "summary": "Excellent match",
            "sections": [
                {
                    "id": "1",
                    "promptRange": {"startLine": 1, "endLine": 2, "text": "Requirement 1"},
                    "status": "matched",
                    "matchConfidence": 100,
                    "semanticLabel": "Core Logic",
                    "notes": "Implemented correctly"
                }
            ],
            "codeSections": [],
            "hiddenKnowledge": [
                {
                    "type": "magic_value",
                    "location": {"startLine": 10, "endLine": 10},
                    "description": "Threshold",
                    "regenerationImpact": "would_differ",
                    "suggestedPromptAddition": "Add threshold"
                }
            ],
            "stats": {
                "totalRequirements": 1,
                "matchedRequirements": 1,
                "missingRequirements": 0,
                "promptToCodeCoverage": 100.0
            }
        },
        "cost": 0.02,
        "model_name": "gpt-4o"
    }
    
    mocker.patch("pdd.llm_invoke.llm_invoke", return_value=mock_llm_result)
    mocker.patch("pdd.load_prompt_template", return_value="Mock prompt template")
    
    response = client.post(
        "/api/v1/prompts/diff-analysis",
        json={
            "prompt_content": "Requirements",
            "code_content": "Code",
            "mode": "detailed"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["overallScore"] == 90
    assert data["result"]["canRegenerate"] is True
    assert data["result"]["hiddenKnowledge"][0]["type"] == "magic_value"

def test_filepath_to_prompt_filename_integration():
    """Verify cross-module path normalization (architecture_sync_helper)."""
    # Test flat structure
    assert filepath_to_prompt_filename("main.py", "Python") == "main_Python.prompt"
    
    # Test nested structure (The key fix from Iteration 3)
    assert filepath_to_prompt_filename("core/utils/helper.ts", "TypeScript") == "core/utils/helper_TypeScript.prompt"
    assert filepath_to_prompt_filename("api/routes/user.py", "Python") == "api/routes/user_Python.prompt"

def test_generate_output_paths_pddrc_integration(tmp_path):
    """Verify generate_output_paths correctly handles .pddrc context config (Issue #617)."""
    # Create the target directory so it's recognized as a directory even without trailing slash
    target_dir = tmp_path / "src" / "modules"
    target_dir.mkdir(parents=True)
    
    # Case 1: Without trailing slash - Preserves basename subdirectory
    context_config_no_slash = {
        "generate_output_path": "src/modules"
    }
    
    paths1 = generate_output_paths(
        command="generate",
        output_locations={},
        basename="auth/login",
        language="python",
        file_extension=".py",
        context_config=context_config_no_slash,
        config_base_dir=str(tmp_path)
    )
    assert paths1["output"].replace("\\", "/").endswith("src/modules/auth/login.py")

    # Case 2: With trailing slash - Flattens to specific directory (Explicit user intent)
    context_config_slash = {
        "generate_output_path": "src/modules/"
    }
    
    paths2 = generate_output_paths(
        command="generate",
        output_locations={},
        basename="auth/login",
        language="python",
        file_extension=".py",
        context_config=context_config_slash,
        config_base_dir=str(tmp_path)
    )
    # Should resolve to: .../src/modules/login.py
    assert paths2["output"].replace("\\", "/").endswith("src/modules/login.py")


def test_websocket_message_integration():
    """Verify WebSocket message models work in an integration flow."""
    now = datetime.now(timezone.utc)
    
    # Test StdoutMessage
    stdout = StdoutMessage(
        data="Process started",
        raw="\x1b[32mProcess started\x1b[0m",
        timestamp=now
    )
    dumped = stdout.model_dump()
    assert dumped["type"] == "stdout"
    assert dumped["data"] == "Process started"
    
    # Test StderrMessage
    stderr = StderrMessage(
        data="Warning: disk low",
        timestamp=now
    )
    dumped = stderr.model_dump()
    assert dumped["type"] == "stderr"
    assert dumped["data"] == "Warning: disk low"
