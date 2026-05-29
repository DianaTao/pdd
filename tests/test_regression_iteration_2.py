import pytest
import tomllib
from pathlib import Path
from pdd.server.models import ServerConfig, ProgressMessage
from pdd.server.routes.prompts import SyncStatusResponse, DiffStats, DiffAnalysisResult
from pdd.server.app import security_exception_handler, validation_exception_handler, generic_exception_handler
from pdd.server.executor import OutputCapture
import inspect
from unittest.mock import MagicMock

def test_dependency_categorization():
    """Verify that test-only and provider-specific SDKs are in optional-dependencies."""
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    
    deps = data["project"]["dependencies"]
    optional_deps = data["project"]["optional-dependencies"]["dev"]
    
    # Provider SDKs and test tools should be in optional_deps
    dev_only = [
        "pytest", "boto3", "google-cloud-aiplatform", "z3-solver",
        "types-PyYAML", "pandas-stubs", "lxml-stubs"
    ]
    for dep in dev_only:
        # Check that it starts with the name (to handle pinning)
        assert any(dep in d for d in optional_deps), f"{dep} should be in optional-dependencies"
        assert not any(dep in d for d in deps), f"{dep} should NOT be in main dependencies"

def test_litellm_version_sync():
    """Verify litellm version is synced between pyproject.toml and requirements.txt."""
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    
    pyproject_litellm = next(d for d in data["project"]["dependencies"] if "litellm" in d)
    
    with open("requirements.txt", "r") as f:
        requirements_content = f.read()
    
    assert pyproject_litellm in requirements_content, "litellm version mismatch between pyproject.toml and requirements.txt"

def test_pydantic_models_instantiation():
    """Verify Pydantic models can be instantiated with named arguments."""
    # ServerConfig
    config = ServerConfig(project_root=Path("."), host="localhost", port=8000)
    assert config.host == "localhost"
    
    # SyncStatusResponse
    ssr = SyncStatusResponse(status="synced", last_sync=None, message="OK")
    assert ssr.status == "synced"
    
    # DiffStats
    ds = DiffStats(
        totalRequirements=10, 
        matchedRequirements=8, 
        missingRequirements=2, 
        promptToCodeCoverage=80.0
    )
    assert ds.totalRequirements == 10
    
    # DiffAnalysisResult
    dar = DiffAnalysisResult(
        overallScore=85, 
        summary="Test summary", 
        stats=ds
    )
    assert dar.overallScore == 85
    
    # ProgressMessage
    pm = ProgressMessage(type="progress", current=50, total=100, message="Loading", data={"extra": "info"})
    assert pm.data == {"extra": "info"}

def test_exception_handler_signatures():
    """Verify exception handlers have the correct Starlette/FastAPI signature (request, exc)."""
    handlers = [security_exception_handler, validation_exception_handler, generic_exception_handler]
    for handler in handlers:
        sig = inspect.signature(handler)
        assert len(sig.parameters) == 2
        params = list(sig.parameters.values())
        assert params[0].name == "request"
        # The second parameter name can vary but it's the exception
        assert params[1].name in ("exc", "e")

def test_executor_exit_return_type():
    """Verify OutputCapture.__exit__ returns None (to propagate exceptions)."""
    capture = OutputCapture()
    # Mocking __enter__ dependencies if necessary, but we just want to check __exit__
    res = capture.__exit__(None, None, None)
    assert res is None

def test_jobs_import():
    """Verify pdd.server.jobs can be imported (resolves name redefinition issues)."""
    import pdd.server.jobs
    assert pdd.server.jobs.JobManager is not None

def test_progress_message_mock_updated():
    """Verify ProgressMessage mock in tests/server/routes/test_websocket.py (if accessible)."""
    # We can't easily import from the test file itself if it's not in a package,
    # but we can check if it exists and has the expected content.
    test_file = Path("tests/server/routes/test_websocket.py")
    if test_file.exists():
        content = test_file.read_text()
        assert "ProgressMessage(WSMessage)" in content
        assert "def __init__(self, current, total, message, timestamp, data=None):" in content
        assert "super().__init__(type=\"progress\", data=data" in content
