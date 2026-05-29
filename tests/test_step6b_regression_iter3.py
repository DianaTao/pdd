
import pytest
import os
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

from pydantic import BaseModel, Field

# 1. Frontend Regression: DependencyViewer.tsx
def test_frontend_fix_dependency_viewer_logic():
    """Verify DependencyViewer.tsx fix exists in the code."""
    path = Path("pdd/frontend/components/DependencyViewer.tsx")
    assert path.exists()
    content = path.read_text()
    # Check for the fix: Map typing and correct position object construction
    assert "new Map<string, { x: number; y: number }>" in content
    assert "position: { x: savedPos.x, y: savedPos.y }" in content

# 2. Codebase Cleanup: Removal of orphan components
def test_orphan_components_removed():
    """Verify that orphan components identified in Step 4/6a were removed."""
    orphans = [
        "pdd/frontend/components/CommandForm.tsx",
        "pdd/frontend/components/CommandOutput.tsx",
        "pdd/frontend/components/GeneratedCommand.tsx",
        "pdd/frontend/components/InputField.tsx",
        "pdd/frontend/components/TextAreaField.tsx"
    ]
    for orphan in orphans:
        assert not Path(orphan).exists(), f"Orphan component {orphan} should have been removed"

# 3. Backend Regression: pdd/server/routes/prompts.py models
from pdd.server.routes.prompts import (
    SyncStatusResponse, DiffAnalysisResult, DiffStats, 
    HiddenKnowledge, HiddenKnowledgeLocation, DiffAnalysisResponse
)

def test_sync_status_response_instantiation():
    """Verify SyncStatusResponse can be instantiated with named arguments."""
    resp = SyncStatusResponse(
        status="in_sync",
        last_sync_timestamp="2026-05-29T12:00:00Z",
        last_sync_command="pdd sync",
        prompt_modified=False,
        code_modified=False,
        fingerprint_exists=True,
        prompt_exists=True,
        code_exists=True
    )
    assert resp.status == "in_sync"

def test_diff_analysis_models_instantiation():
    """Verify Diff analysis models can be instantiated correctly (Regression for Iteration 3)."""
    stats = DiffStats(
        totalRequirements=10,
        matchedRequirements=8,
        missingRequirements=2,
        totalCodeFeatures=5,
        documentedFeatures=4,
        undocumentedFeatures=1,
        promptToCodeCoverage=80.0,
        codeToPromptCoverage=80.0,
        hiddenKnowledgeCount=1,
        criticalGaps=0
    )
    
    hk = HiddenKnowledge(
        type="magic_value",
        location=HiddenKnowledgeLocation(startLine=10, endLine=10),
        description="Threshold value",
        regenerationImpact="would_differ",
        suggestedPromptAddition="Add threshold=0.5 to prompt"
    )
    
    result = DiffAnalysisResult(
        overallScore=85,
        canRegenerate=True,
        regenerationRisk="low",
        promptToCodeScore=90,
        codeToPromptScore=80,
        summary="Good alignment",
        sections=[],
        codeSections=[],
        hiddenKnowledge=[hk],
        lineMappings=[],
        stats=stats,
        missing=[],
        extra=[],
        suggestions=[]
    )
    
    response = DiffAnalysisResponse(
        result=result,
        cost=0.01,
        model="test-model",
        analysisMode="detailed",
        cached=False,
        tests_included=True,
        test_files=["test_a.py"]
    )
    
    assert response.result.overallScore == 85
    assert response.result.hiddenKnowledge[0].type == "magic_value"

# 4. Backend Regression: ServerConfig in models.py (used by app.py and connect.py)
from pdd.server.models import ServerConfig

def test_server_config_instantiation():
    """Verify ServerConfig can be instantiated with all fields as used in app.py and connect.py."""
    config = ServerConfig(
        host="127.0.0.1",
        port=9876,
        token="secret-token",
        allow_remote=False,
        allowed_origins=["http://localhost:3000"],
        log_level="debug"
    )
    assert config.port == 9876
    assert config.token == "secret-token"

# 5. Backend Regression: websocket.py models (StdoutMessage, StderrMessage)
from pdd.server.models import StdoutMessage, StderrMessage

def test_websocket_message_models():
    """Verify StdoutMessage and StderrMessage can be instantiated (used in websocket.py)."""
    stdout = StdoutMessage(
        data="hello",
        raw="\x1b[32mhello\x1b[0m",
        timestamp=datetime.now(timezone.utc)
    )
    assert stdout.type == "stdout"
    assert stdout.data == "hello"
    
    stderr = StderrMessage(
        data="error",
        raw="error",
        timestamp=datetime.now(timezone.utc)
    )
    assert stderr.type == "stderr"
    assert stderr.data == "error"
