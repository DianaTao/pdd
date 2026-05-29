import json
from pathlib import Path
from click.testing import CliRunner
from fastapi.testclient import TestClient
import pytest

from pdd.cli import cli
from pdd.server.app import create_app
from pdd.evidence_store import sha256_file

@pytest.fixture
def temp_project(tmp_path: Path):
    project = tmp_path
    (project / ".pdd").mkdir()
    return project

def test_gate_cli_e2e(temp_project: Path):
    """E2E test for 'pdd checkup gate' CLI command verifying skip policy."""
    # We use isolated_filesystem for the runner
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=temp_project):
        cwd = Path.cwd()
        
        # Setup files inside isolated filesystem
        (cwd / ".pdd").mkdir(exist_ok=True)
        (cwd / "src").mkdir(exist_ok=True)
        code = cwd / "src" / "refund.py"
        code.write_text("def refund():\n    return 1\n", encoding="utf-8")
        
        manifest_path = cwd / ".pdd" / "evidence" / "devunits" / "refund.latest.json"
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
        
        # Case 1: Skips not allowed (should fail)
        policy_file = cwd / "policy.yml"
        policy_file.write_text(
            "allow:\n  skipped_verify: false\n  skipped_tests: false\n",
            encoding="utf-8",
        )
        
        result = runner.invoke(cli, ["checkup", "gate", "refund", "--policy", "policy.yml"])
        assert result.exit_code != 0
        assert "PDD gate failed" in result.output
        assert "refund: verify was skipped against policy" in result.output
        assert "refund: unit tests were skipped against policy" in result.output

        # Case 2: Skips allowed (should pass)
        policy_file.write_text(
            "allow:\n  skipped_verify: true\n  skipped_tests: true\n",
            encoding="utf-8",
        )
        result = runner.invoke(cli, ["checkup", "gate", "refund", "--policy", "policy.yml"])
        assert result.exit_code == 0
        assert "PDD gate passed" in result.output

def test_server_status_api_e2e(temp_project: Path):
    """Integration test for /api/v1/status endpoint."""
    app = create_app(temp_project)
    client = TestClient(app)
    
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["project_root"] == str(temp_project.resolve())

def test_prompts_sync_status_api_e2e(temp_project: Path):
    """Integration test for /api/v1/prompts/sync-status endpoint."""
    app = create_app(temp_project)
    client = TestClient(app)
    
    response = client.get("/api/v1/prompts/sync-status?basename=test&language=python")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "never_synced"

def test_websocket_watch_interaction_e2e(temp_project: Path):
    """Integration test for WebSocket /ws/watch interaction."""
    app = create_app(temp_project)
    client = TestClient(app)
    
    with client.websocket_connect("/ws/watch") as websocket:
        # Client must send subscription message first
        websocket.send_text(json.dumps({"paths": ["."]}))
        # If we reach here without WebSocketDisconnect, it's successful connection and subscription
        pass
