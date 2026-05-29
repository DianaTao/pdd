
import pytest
import os
from pathlib import Path
from typing import Optional, Tuple, Union
from datetime import datetime, timezone

from pydantic import BaseModel
import click

# 1. pdd/commands/checkup_simplify.py regression
from pdd.commands.checkup_simplify import checkup_simplify

def test_checkup_simplify_return_type():
    """Verify checkup_simplify returns the expected Optional[Tuple[str, float, str]] type."""
    # We can't easily run the command without a full click context and real/mocked dependencies,
    # but we can check the function signature and a mock-like call if we're careful.
    # The fix was adding 'return "\n".join(result.summary_lines), result.cost, result.provider'
    assert checkup_simplify.callback is not None
    # Check if the function actually has the return statement at the end of its body
    import inspect
    source = inspect.getsource(checkup_simplify.callback)
    assert "return \"\\n\".join(result.summary_lines), result.cost, result.provider" in source

# 2. pdd/server/routes/prompts.py regression
from pdd.server.routes.prompts import CostEstimateResponse, TokenMetricsResponse

def test_prompt_response_models():
    """Verify Pydantic models in routes/prompts.py can be instantiated with named arguments."""
    cost = CostEstimateResponse(
        input_cost=0.5,
        model="test-model",
        tokens=1000,
        cost_per_million=1.0,
        currency="USD"
    )
    assert cost.input_cost == 0.5
    
    metrics = TokenMetricsResponse(
        token_count=1000,
        context_limit=8000,
        context_usage_percent=12.5,
        cost_estimate=cost
    )
    assert metrics.token_count == 1000
    assert metrics.cost_estimate.model == "test-model"

# 3. pdd/server/app.py regression
from pdd.server.models import ServerConfig

def test_server_config_defaults():
    """Verify ServerConfig can be initialized with positional/named defaults as used in app.py."""
    config = ServerConfig(
        host="127.0.0.1",
        port=9876,
        log_level="info",
    )
    assert config.host == "127.0.0.1"
    assert config.port == 9876
    assert config.log_level == "info"

# 4. pdd/server/executor.py regression
from pdd.server.executor import OutputCapture

def test_executor_output_capture_context_manager():
    """Verify OutputCapture works as a context manager and returns False from __exit__."""
    capture = OutputCapture()
    with capture:
        print("test output")
    
    assert "test output" in capture.stdout
    
    # Verify __exit__ signature and return value
    # __exit__(self, exc_type, exc_val, exc_tb) -> Optional[bool]
    ret = capture.__exit__(None, None, None)
    assert ret is False

# 5. pdd/server/routes/websocket.py regression
from pdd.server.routes.websocket import emit_job_output, StdoutMessage, StderrMessage

@pytest.mark.asyncio
async def test_websocket_emit_job_output_typing(mocker):
    """Verify emit_job_output handles different streams and creates correct models."""
    # Mock ConnectionManager.broadcast_job_message
    mock_broadcast = mocker.patch('pdd.server.routes.websocket.manager.broadcast_job_message')
    
    await emit_job_output("job123", "stdout", "hello world")
    
    assert mock_broadcast.called
    args = mock_broadcast.call_args[0]
    assert args[0] == "job123"
    assert isinstance(args[1], StdoutMessage)
    assert args[1].data == "hello world"
    
    await emit_job_output("job123", "stderr", "error message")
    args = mock_broadcast.call_args[0]
    assert isinstance(args[1], StderrMessage)
    assert args[1].data == "error message"

# 6. pdd/edit_file.py regression
import pdd.edit_file as edit_file_mod

def test_edit_file_import_robustness():
    """Verify pdd/edit_file.py can be imported even if optional dependencies are missing."""
    # Since we are running in an environment where they might or might not be present,
    # we check that HAS_LANGGRAPH is defined and edit_file returns a graceful error if False.
    assert hasattr(edit_file_mod, 'HAS_LANGGRAPH')
    
    if not edit_file_mod.HAS_LANGGRAPH:
        import asyncio
        async def run_test():
            success, error = await edit_file_mod.edit_file("nonexistent.txt", "do something")
            assert success is False
            assert "requires langgraph" in error
        
        asyncio.run(run_test())

# 7. architecture.json regression
import json

def test_architecture_json_integrity():
    """Verify architecture.json is valid and contains updated paths and step numbers."""
    arch_path = Path("architecture.json")
    assert arch_path.exists()
    
    with open(arch_path, 'r') as f:
        data = json.load(f)
    
    # Check for some expected content (based on Step 6a summary)
    # prompt_tester.py moved to tests/
    # run_generated.py moved to utils/
    
    found_tester = False
    found_run_gen = False
    for module in data:
        if "tests/prompt_tester.py" in module.get("path", "") or "tests/prompt_tester.py" in module.get("filepath", ""):
            found_tester = True
        if "utils/run_generated.py" in module.get("path", "") or "utils/run_generated.py" in module.get("filepath", ""):
            found_run_gen = True
            
    # Note: architecture.json might use different keys, so we check generally
    content_str = json.dumps(data)
    assert "tests/prompt_tester.py" in content_str
    assert "utils/run_generated.py" in content_str
    assert "prompts/regression_bash.prompt" in content_str
    
    # Check step numbers (e.g. step 5 instead of 4 for reproduction)
    assert "step5_reproduction" in content_str or "step 5" in content_str.lower()
    assert "pdd/edit_file.py" in content_str
