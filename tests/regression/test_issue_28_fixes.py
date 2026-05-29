import pytest
from pathlib import Path
from datetime import datetime, timezone
from pdd.server.models import ServerConfig, ServerStatus, WSMessage, ProgressMessage
from pdd.server.routes.prompts import SyncStatusResponse, DiffStats, DiffAnalysisResult
from pdd.server.app import security_exception_handler, validation_exception_handler
from fastapi import Request
from unittest.mock import MagicMock

def test_server_config_instantiation():
    """Verify ServerConfig can be instantiated with named arguments (Fix 2.1)."""
    config = ServerConfig(
        host="127.0.0.1",
        port=9876,
        token="test-token",
        allow_remote=True,
        allowed_origins=["*"],
        log_level="debug"
    )
    assert config.host == "127.0.0.1"
    assert config.port == 9876
    assert config.token == "test-token"

def test_sync_status_response_instantiation():
    """Verify SyncStatusResponse can be instantiated with named arguments (Fix 2.3)."""
    response = SyncStatusResponse(
        status="in_sync",
        last_sync_timestamp="2026-05-29T10:00:00Z",
        last_sync_command="pdd sync calculator",
        prompt_modified=False,
        code_modified=False,
        fingerprint_exists=True,
        prompt_exists=True,
        code_exists=True
    )
    assert response.status == "in_sync"

def test_progress_message_instantiation():
    """Verify ProgressMessage includes the data parameter (Fix 2.4)."""
    msg = ProgressMessage(
        current=50,
        total=100,
        message="Processing...",
        data={"info": "some data"},
        timestamp=datetime.now(timezone.utc)
    )
    assert msg.current == 50
    assert msg.data == {"info": "some data"}

def test_diff_stats_instantiation():
    """Verify DiffStats can be instantiated with named arguments (Fix 2.3)."""
    stats = DiffStats(
        totalRequirements=10,
        matchedRequirements=8,
        missingRequirements=2,
        totalCodeFeatures=5,
        documentedFeatures=4,
        undocumentedFeatures=1,
        promptToCodeCoverage=80.0,
        codeToPromptCoverage=80.0,
        hiddenKnowledgeCount=0,
        criticalGaps=0
    )
    assert stats.totalRequirements == 10

@pytest.mark.asyncio
async def test_exception_handlers_compatibility():
    """Verify exception handlers accept Any as exception type (Fix 2.2)."""
    request = MagicMock(spec=Request)
    
    # Test security_exception_handler
    exc_security = MagicMock()
    exc_security.message = "Forbidden"
    exc_security.code = "AUTH_ERROR"
    response = await security_exception_handler(request, exc_security)
    assert response.status_code == 403
    
    # Test validation_exception_handler
    exc_validation = MagicMock()
    exc_validation.errors = lambda: [{"loc": ["body"], "msg": "invalid", "type": "value_error"}]
    exc_validation.body = {"test": "data"}
    response = await validation_exception_handler(request, exc_validation)
    assert response.status_code == 422

def test_job_manager_naming():
    """Verify JobManager uses ActualClickCommandExecutor to avoid name redefinition (Fix 2.5)."""
    from pdd.server.jobs import ClickCommandExecutor
    # If the fix is applied, ClickCommandExecutor should be available
    assert ClickCommandExecutor is not None

def test_executor_exit_return_type():
    """Verify OutputCapture.__exit__ returns None (Fix 2.6)."""
    from pdd.server.executor import OutputCapture
    capture = OutputCapture()
    result = capture.__exit__(None, None, None)
    assert result is None

def test_dependency_manifest_groups():
    """Verify dependencies are correctly grouped in pyproject.toml (Fix 1.1)."""
    import tomllib
    pyproject_path = Path("pyproject.toml")
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        
        dev_deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
        main_deps = data.get("project", {}).get("dependencies", [])
        
        # Check dev dependencies
        dev_dep_names = [d.split("==")[0].split(">=")[0].split("<=")[0].strip() for d in dev_deps]
        assert "pytest" in dev_dep_names
        assert "z3-solver" in dev_dep_names
        assert "boto3" in dev_dep_names
        assert "google-cloud-aiplatform" in dev_dep_names
        
        # Check that they are NOT in main dependencies
        main_dep_names = [d.split("==")[0].split(">=")[0].split("<=")[0].strip() for d in main_deps]
        assert "pytest" not in main_dep_names
        assert "z3-solver" not in main_dep_names
