from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from fastapi import APIRouter, Depends, HTTPException
    from pydantic import BaseModel, Field
except ImportError:
    # Optional dependencies for environments where server is not run
    pass

from rich.console import Console

from ...architecture_sync import (
    generate_tags_from_architecture,
    get_architecture_entry_for_prompt,
    has_pdd_tags,
    sync_all_prompts_to_architecture,
    sync_prompts_to_architecture,
)
from ...agentic_common import run_agentic_task
from ...load_prompt_template import load_prompt_template
from ..app import get_app_state, AppState


console = Console()
executor = ThreadPoolExecutor(max_workers=2)
router = APIRouter(prefix="/api/v1/architecture", tags=["architecture"])


# ============================================================================
# Pydantic Models
# ============================================================================

class ContractSummary(BaseModel):
    rules: List[str]
    critical: List[str]
    stories: List[str]
    capabilities: List[str]
    coverage_status: str
    evidence_status: str
    waived: List[str]


class ArchitectureModule(BaseModel):
    reason: str
    description: str
    dependencies: List[str]
    priority: int
    filename: str
    filepath: str
    tags: List[str] = Field(default_factory=list)
    interface: Optional[Dict[str, Any]] = None
    contract_summary: Optional[ContractSummary] = None


class ValidationError(BaseModel):
    type: str  # circular_dependency, missing_dependency, invalid_field
    message: str
    modules: List[str]


class ValidationWarning(BaseModel):
    type: str  # duplicate_dependency, orphan_module
    message: str
    modules: List[str]


class ValidateArchitectureRequest(BaseModel):
    modules: List[ArchitectureModule]


class ValidationResult(BaseModel):
    valid: bool  # True if no errors (warnings OK)
    errors: List[ValidationError]
    warnings: List[ValidationWarning]


class SyncRequest(BaseModel):
    filenames: Optional[List[str]] = None  # None = sync all
    dry_run: bool = False


class SyncResult(BaseModel):
    success: bool
    updated_count: int
    skipped_count: int = 0
    results: List[Dict[str, Any]]
    validation: ValidationResult
    errors: List[str] = Field(default_factory=list)


class GenerateTagsRequest(BaseModel):
    prompt_filename: str


class GenerateTagsResult(BaseModel):
    success: bool
    tags: Optional[str] = None
    has_existing_tags: bool = False
    architecture_entry: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class RearrangeRequest(BaseModel):
    architecture_path: str = Field(
        "architecture.json",
        description="Path to architecture file, relative to project root"
    )


class RearrangeResult(BaseModel):
    success: bool
    modules: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def _detect_cycles(modules: List[ArchitectureModule]) -> List[List[str]]:
    """Detect all circular dependencies using DFS."""
    graph = {m.filename: m.dependencies for m in modules}
    cycles = []
    visited = set()
    stack = []
    
    def dfs(node: str):
        if node in stack:
            cycle_start = stack.index(node)
            cycles.append(stack[cycle_start:] + [node])
            return
        if node in visited:
            return
            
        visited.add(node)
        stack.append(node)
        
        for neighbor in graph.get(node, []):
            dfs(neighbor)
            
        stack.pop()
        
    for module in graph:
        dfs(module)
        
    return cycles


def _validate_architecture(modules: List[ArchitectureModule]) -> ValidationResult:
    """Core validation logic for architecture.json."""
    errors = []
    warnings = []
    
    module_names = {m.filename for m in modules}
    depended_upon = set()
    
    # Missing, duplicates, and invalid fields
    for mod in modules:
        if not mod.filename or not mod.filepath or not mod.description:
            errors.append(ValidationError(
                type="invalid_field",
                message=f"Module {mod.filename} is missing required fields (filename, filepath, description).",
                modules=[mod.filename]
            ))
            
        seen_deps = set()
        for dep in mod.dependencies:
            depended_upon.add(dep)
            if dep not in module_names:
                errors.append(ValidationError(
                    type="missing_dependency",
                    message=f"Module {mod.filename} depends on missing module {dep}.",
                    modules=[mod.filename, dep]
                ))
            if dep in seen_deps:
                warnings.append(ValidationWarning(
                    type="duplicate_dependency",
                    message=f"Module {mod.filename} lists dependency {dep} multiple times.",
                    modules=[mod.filename]
                ))
            seen_deps.add(dep)
            
    # Orphans
    for mod in modules:
        if not mod.dependencies and mod.filename not in depended_upon:
            warnings.append(ValidationWarning(
                type="orphan_module",
                message=f"Module {mod.filename} is an orphan (no dependencies, not depended upon).",
                modules=[mod.filename]
            ))
            
    # Cycles
    cycles = _detect_cycles(modules)
    for cycle in cycles:
        errors.append(ValidationError(
            type="circular_dependency",
            message=f"Circular dependency detected: {' -> '.join(cycle)}",
            modules=list(set(cycle))
        ))
        
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


# ============================================================================
# Routes
# ============================================================================

@router.post("/validate", response_model=ValidationResult)
async def validate_architecture(request: ValidateArchitectureRequest):
    """Validate architecture for structural issues."""
    return _validate_architecture(request.modules)


@router.post("/sync-from-prompts", response_model=SyncResult)
async def sync_from_prompts(
    request: SyncRequest,
    state: AppState = Depends(get_app_state)
):
    """Sync architecture.json from PDD metadata tags in prompt files."""
    arch_path = state.project_root / "architecture.json"
    prompts_dir = state.project_root / "prompts"
    
    try:
        if request.filenames is None:
            result = sync_all_prompts_to_architecture(
                prompts_dir=prompts_dir,
                architecture_path=arch_path,
                dry_run=request.dry_run
            )
        else:
            result = sync_prompts_to_architecture(
                filenames=request.filenames,
                prompts_dir=prompts_dir,
                architecture_path=arch_path,
                dry_run=request.dry_run
            )
            
        # Validate the resulting architecture
        arch_data = json.loads(arch_path.read_text(encoding="utf-8")) if arch_path.exists() else []
        modules = [ArchitectureModule(**m) for m in arch_data]
        validation = _validate_architecture(modules)
        
        return SyncResult(
            success=result.get("success", False),
            updated_count=result.get("updated_count", 0),
            skipped_count=result.get("skipped_count", 0),
            results=result.get("results", []),
            validation=validation,
            errors=result.get("errors", [])
        )
    except Exception as e:
        console.print(f"[bold red]Sync Error:[/bold red] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-tags-for-prompt", response_model=GenerateTagsResult)
async def generate_tags_for_prompt(
    request: GenerateTagsRequest,
    state: AppState = Depends(get_app_state)
):
    """Generate PDD metadata tags for prompts from architecture.json."""
    arch_path = state.project_root / "architecture.json"
    prompt_path = state.project_root / "prompts" / request.prompt_filename
    
    try:
        has_tags = False
        if prompt_path.exists():
            content = prompt_path.read_text(encoding="utf-8")
            has_tags = has_pdd_tags(content)
            
        entry = get_architecture_entry_for_prompt(request.prompt_filename, architecture_path=arch_path)
        if not entry:
            return GenerateTagsResult(
                success=False,
                error=f"No architecture entry found for {request.prompt_filename}",
                has_existing_tags=has_tags
            )
            
        tags = generate_tags_from_architecture(entry)
        return GenerateTagsResult(
            success=True,
            tags=tags,
            has_existing_tags=has_tags,
            architecture_entry=entry
        )
    except Exception as e:
        console.print(f"[bold red]Generate Tags Error:[/bold red] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rearrange", response_model=RearrangeResult)
async def rearrange_graph_layout(
    request: RearrangeRequest,
    state: AppState = Depends(get_app_state)
):
    """Run an agentic task to rearrange the architecture layout."""
    arch_full_path = state.project_root / request.architecture_path
    original_content = None
    if arch_full_path.exists():
        original_content = arch_full_path.read_text(encoding="utf-8")

    try:
        prompt_content = load_prompt_template(
            "arrange_graph_layout_LLM.prompt",
            project_root=str(state.project_root),
            architecture_path=request.architecture_path
        )
        
        loop = asyncio.get_event_loop()
        success, output, _, _ = await loop.run_in_executor(
            executor,
            run_agentic_task,
            prompt_content,
            state.project_root,
            False,
            1
        )
        
        if not success:
            return RearrangeResult(
                success=False,
                error=f"Agentic task failed: {output}"
            )
            
        if arch_full_path.exists():
            # Read the NEW content generated by the agent
            new_modules_data = json.loads(arch_full_path.read_text(encoding="utf-8"))
            
            # RESTORE the original content if it existed (as per test requirements)
            if original_content is not None:
                arch_full_path.write_text(original_content, encoding="utf-8")
                
            return RearrangeResult(
                success=True,
                modules=new_modules_data,
                message="Rearranged successfully."
            )
        else:
            return RearrangeResult(
                success=False,
                error="Architecture file missing after task completion."
            )
            
    except Exception as e:
        console.print(f"[bold red]Rearrange Error:[/bold red] {e}")
        # Attempt to restore on error too
        if original_content is not None and arch_full_path.exists():
             arch_full_path.write_text(original_content, encoding="utf-8")
        raise HTTPException(status_code=500, detail=str(e))