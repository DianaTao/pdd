"""
Test Plan for pdd/server/routes/architecture.py

1. **Unit Tests**:
    - **Valid Architecture**: Verify a standard dependency tree (A->B, A->C) passes validation with no errors or warnings.
    - **Circular Dependencies**:
        - Direct cycle (A->B->A).
        - Self cycle (A->A).
        - Deep cycle (A->B->C->A).
        - Verify that `valid=False` and error type is `circular_dependency`.
        - Verify the reported cycle path structure.
    - **Missing Dependencies**:
        - Module depends on a filename that doesn't exist in the module list.
        - Verify `valid=False` and error type is `missing_dependency`.
    - **Invalid Fields**:
        - Test empty `filename`, `filepath`, `description`.
        - Verify `valid=False` and error type is `invalid_field`.
    - **Warnings**:
        - **Duplicate Dependencies**: Module lists same dependency twice. Verify `valid=True` (if no errors) and warning present.
        - **Orphan Modules**: Module with no dependencies and no incoming edges. Verify `valid=True` and warning present.
    - **Complex Mixed Case**:
        - Combination of valid modules, orphans, and cycles to ensure all are reported correctly in the result.

2. **Formal Verification (Z3)**:
    - **DAG Generation**: Use Z3 to synthesize a non-trivial Directed Acyclic Graph (DAG) structure.
    - **Cycle Generation**: Use Z3 to synthesize a graph structure that contains a cycle of a specific length.
"""

import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from typing import List, Dict, Any
from pathlib import Path

from pdd.server.routes.architecture import (
    validate_architecture,
    ValidateArchitectureRequest,
    ArchitectureModule,
    ValidationResult,
    ValidationError,
    ValidationWarning,
    SyncRequest,
    sync_from_prompts,
    generate_tags_for_prompt,
    GenerateTagsRequest,
    rearrange_graph_layout,
    RearrangeRequest,
)

# Helper to create modules quickly
def create_module(
    filename: str, 
    dependencies: List[str] = None, 
    description: str = "desc", 
    filepath: str = None
) -> ArchitectureModule:
    if dependencies is None:
        dependencies = []
    if filepath is None:
        filepath = f"src/{filename}"
    
    return ArchitectureModule(
        reason="test",
        description=description,
        dependencies=dependencies,
        priority=1,
        filename=filename,
        filepath=filepath,
        tags=[],
        interface={}
    )

@pytest.mark.asyncio
async def test_validate_architecture_valid_simple():
    """Test a simple valid dependency chain A -> B -> C."""
    modules = [
        create_module("A.py", ["B.py"]),
        create_module("B.py", ["C.py"]),
        create_module("C.py", [])
    ]
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    
    assert result.valid is True
    assert len(result.errors) == 0
    assert len(result.warnings) == 0

@pytest.mark.asyncio
async def test_validate_architecture_circular_direct():
    """Test detection of a direct circular dependency A -> B -> A."""
    modules = [
        create_module("A.py", ["B.py"]),
        create_module("B.py", ["A.py"])
    ]
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    
    assert result.valid is False
    assert len(result.errors) > 0
    
    circle_errors = [e for e in result.errors if e.type == "circular_dependency"]
    assert len(circle_errors) >= 1
    
    cycle_modules = set(circle_errors[0].modules)
    assert "A.py" in cycle_modules
    assert "B.py" in cycle_modules

@pytest.mark.asyncio
async def test_validate_architecture_circular_self():
    """Test detection of a self-referencing module A -> A."""
    modules = [
        create_module("A.py", ["A.py"])
    ]
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    
    assert result.valid is False
    circle_errors = [e for e in result.errors if e.type == "circular_dependency"]
    assert len(circle_errors) == 1
    assert "A.py" in circle_errors[0].modules

@pytest.mark.asyncio
async def test_validate_architecture_missing_dependency():
    """Test detection of dependencies on non-existent modules."""
    modules = [
        create_module("A.py", ["NonExistent.py"])
    ]
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    
    assert result.valid is False
    missing_errors = [e for e in result.errors if e.type == "missing_dependency"]
    assert len(missing_errors) == 1
    assert "NonExistent.py" in missing_errors[0].message
    assert "A.py" in missing_errors[0].modules

@pytest.mark.asyncio
async def test_validate_architecture_invalid_fields():
    """Test validation of required fields (filename, filepath, description)."""
    modules = [
        create_module("", [], description="valid", filepath="valid"),  # Empty filename
        create_module("B.py", [], description="", filepath="valid"),   # Empty description
        create_module("C.py", [], description="valid", filepath=""),   # Empty filepath
    ]
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    
    assert result.valid is False
    field_errors = [e for e in result.errors if e.type == "invalid_field"]
    assert len(field_errors) == 3

@pytest.mark.asyncio
async def test_validate_architecture_duplicate_dependency_warning():
    """Test warning generation for duplicate dependencies."""
    modules = [
        create_module("A.py", ["B.py", "B.py"]),
        create_module("B.py", [])
    ]
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    
    assert result.valid is True
    assert len(result.errors) == 0
    
    warnings = [w for w in result.warnings if w.type == "duplicate_dependency"]
    assert len(warnings) == 1
    assert "B.py" in warnings[0].message
    assert warnings[0].modules == ["A.py"]

@pytest.mark.asyncio
async def test_validate_architecture_orphan_module_warning():
    """Test warning generation for orphan modules (no deps, no incoming edges)."""
    modules = [
        create_module("Connected1.py", ["Connected2.py"]),
        create_module("Connected2.py", []),
        create_module("Orphan.py", [])  # No outgoing, no incoming
    ]
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    
    assert result.valid is True
    warnings = [w for w in result.warnings if w.type == "orphan_module"]
    assert len(warnings) == 1
    assert warnings[0].modules == ["Orphan.py"]

@pytest.mark.asyncio
async def test_generate_tags_for_prompt_success(tmp_path):
    """Success path should read prompt files from project_root/prompts."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "core_python.prompt").write_text(
        "<pdd-reason>Existing tag</pdd-reason>",
        encoding="utf-8",
    )

    entry = {
        "filename": "core_python.prompt",
        "reason": "Core reason",
        "description": "Core module",
        "dependencies": [],
        "priority": 1,
        "filepath": "core.py",
    }

    mock_state = MagicMock()
    mock_state.project_root = tmp_path

    with (
        patch("pdd.server.routes.architecture.get_app_state", return_value=mock_state),
        patch("pdd.server.routes.architecture.get_architecture_entry_for_prompt", return_value=entry),
        patch("pdd.server.routes.architecture.generate_tags_from_architecture", return_value="<pdd-reason>Core reason</pdd-reason>"),
    ):
        result = await generate_tags_for_prompt(
            GenerateTagsRequest(prompt_filename="core_python.prompt"),
            state=mock_state
        )

    assert result.success is True
    assert result.tags == "<pdd-reason>Core reason</pdd-reason>"
    assert result.has_existing_tags is True
    assert result.architecture_entry == entry

@pytest.mark.asyncio
async def test_rearrange_does_not_mutate_file(tmp_path):
    """
    rearrange_graph_layout must restore the architecture file on disk after the
    LLM runs.
    """
    original_modules = [{"filename": "a.py", "position": {"x": 10, "y": 20}}]
    new_modules = [{"filename": "a.py", "position": {"x": 100, "y": 200}}]

    arch_file = tmp_path / "architecture.json"
    arch_file.write_text(json.dumps(original_modules), encoding="utf-8")

    def fake_run_agentic_task(instruction, cwd, verbose, max_retries):
        # Simulate the LLM rewriting the file with new positions
        arch_file.write_text(json.dumps(new_modules), encoding="utf-8")
        return (True, "layout done", 0.1, "mock")

    mock_state = MagicMock()
    mock_state.project_root = tmp_path

    with (
        patch("pdd.server.routes.architecture.get_app_state", return_value=mock_state),
        patch(
            "pdd.server.routes.architecture.run_agentic_task",
            side_effect=fake_run_agentic_task,
        ),
        patch(
            "pdd.server.routes.architecture.load_prompt_template",
            return_value="layout {project_root} {architecture_path}",
        ),
    ):
        request = RearrangeRequest(architecture_path="architecture.json")
        result = await rearrange_graph_layout(request, state=mock_state)

    # File on disk must have ORIGINAL content (restored after LLM ran)
    disk_content = json.loads(arch_file.read_text(encoding="utf-8"))
    assert disk_content == original_modules, (
        "rearrange_graph_layout mutated the file on disk (snapshot was not restored)"
    )

    # Returned result must have the NEW positions from the LLM
    assert result.success is True
    assert result.modules is not None
    assert result.modules[0]["position"]["x"] == 100

@pytest.mark.asyncio
async def test_sync_from_prompts_all(tmp_path):
    """Test sync-from-prompts with no filenames (sync all)."""
    mock_state = MagicMock()
    mock_state.project_root = tmp_path
    
    mock_result = {"success": True, "updated_count": 5, "results": []}
    
    with (
        patch("pdd.server.routes.architecture.get_app_state", return_value=mock_state),
        patch("pdd.server.routes.architecture.sync_all_prompts_to_architecture", return_value=mock_result),
    ):
        request = SyncRequest(filenames=None)
        result = await sync_from_prompts(request, state=mock_state)
        
    assert result.success is True
    assert result.updated_count == 5

@pytest.mark.asyncio
async def test_sync_from_prompts_specific(tmp_path):
    """Test sync-from-prompts with specific filenames."""
    mock_state = MagicMock()
    mock_state.project_root = tmp_path
    
    mock_result = {"success": True, "updated_count": 1, "results": []}
    
    with (
        patch("pdd.server.routes.architecture.get_app_state", return_value=mock_state),
        patch("pdd.server.routes.architecture.sync_prompts_to_architecture", return_value=mock_result),
    ):
        request = SyncRequest(filenames=["test.prompt"])
        result = await sync_from_prompts(request, state=mock_state)
        
    assert result.success is True
    assert result.updated_count == 1

@pytest.mark.asyncio
async def test_generate_tags_no_entry(tmp_path):
    """Test generate-tags when no architecture entry exists."""
    mock_state = MagicMock()
    mock_state.project_root = tmp_path
    
    with (
        patch("pdd.server.routes.architecture.get_app_state", return_value=mock_state),
        patch("pdd.server.routes.architecture.get_architecture_entry_for_prompt", return_value=None),
    ):
        request = GenerateTagsRequest(prompt_filename="missing.prompt")
        result = await generate_tags_for_prompt(request, state=mock_state)
        
    assert result.success is False
    assert "No architecture entry found" in result.error

@pytest.mark.asyncio
async def test_rearrange_failure(tmp_path):
    """Test rearrange when the agentic task fails."""
    mock_state = MagicMock()
    mock_state.project_root = tmp_path
    
    with (
        patch("pdd.server.routes.architecture.get_app_state", return_value=mock_state),
        patch("pdd.server.routes.architecture.run_agentic_task", return_value=(False, "error message", 0.0, "mock")),
        patch("pdd.server.routes.architecture.load_prompt_template", return_value="template"),
    ):
        request = RearrangeRequest()
        result = await rearrange_graph_layout(request, state=mock_state)
        
    assert result.success is False
    assert "Agentic task failed" in result.error

@pytest.mark.asyncio
async def test_rearrange_missing_file(tmp_path):
    """Test rearrange when architecture file is missing after task."""
    mock_state = MagicMock()
    mock_state.project_root = tmp_path
    
    with (
        patch("pdd.server.routes.architecture.get_app_state", return_value=mock_state),
        patch("pdd.server.routes.architecture.run_agentic_task", return_value=(True, "done", 0.0, "mock")),
        patch("pdd.server.routes.architecture.load_prompt_template", return_value="template"),
    ):
        request = RearrangeRequest(architecture_path="non_existent.json")
        result = await rearrange_graph_layout(request, state=mock_state)
        
    assert result.success is False
    assert "Architecture file missing" in result.error

# -----------------------------------------------------------------------------
# Z3 Formal Verification Tests
# -----------------------------------------------------------------------------

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

@pytest.mark.skipif(not Z3_AVAILABLE, reason="z3-solver not installed")
@pytest.mark.asyncio
async def test_z3_generated_dag_is_valid():
    """Formal Verification using Z3 to generate a DAG."""
    solver = z3.Solver()
    N = 5
    nodes = [f"Node_{i}" for i in range(N)]
    edges = [[z3.Bool(f"e_{i}_{j}") for j in range(N)] for i in range(N)]
    ranks = [z3.Int(f"r_{i}") for i in range(N)]
    for i in range(N):
        solver.add(z3.Not(edges[i][i]))
        for j in range(N):
            solver.add(z3.Implies(edges[i][j], ranks[i] < ranks[j]))
    edge_count = z3.Sum([z3.If(edges[i][j], 1, 0) for i in range(N) for j in range(N)])
    solver.add(edge_count >= N - 1)
    
    assert solver.check() == z3.sat
    model = solver.model()
    modules = []
    for i in range(N):
        deps = []
        for j in range(N):
            if z3.is_true(model.evaluate(edges[i][j])):
                deps.append(nodes[j])
        modules.append(create_module(nodes[i], deps))
        
    request = ValidateArchitectureRequest(modules=modules)
    result = await validate_architecture(request)
    assert result.valid is True
    assert len([e for e in result.errors if e.type == "circular_dependency"]) == 0
