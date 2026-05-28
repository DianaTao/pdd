from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from .agentic_common import run_agentic_task
from .load_prompt_template import load_prompt_template

console = Console()

IGNORED_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".idea", ".vscode", ".pdd"}

def _get_file_mtimes(root: Path) -> dict[Path, float]:
    """Recursively scan directory to record file modification times."""
    mtimes = {}
    if not root.exists():
        return mtimes
    
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # Skip ignored directories
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        try:
            mtimes[path] = path.stat().st_mtime
        except OSError:
            pass
    return mtimes

def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Extract JSON object from text (handles markdown code blocks and raw JSON)."""
    # Look for markdown JSON block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return dict(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass
            
    # Fallback to finding the first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return dict(json.loads(text[start:end+1]))
        except json.JSONDecodeError:
            pass
            
    return None

def _read_generated_test_file(test_file: Path) -> str:
    """Read the generated test file content if it exists, empty string otherwise."""
    if test_file.exists() and test_file.is_file():
        try:
            return test_file.read_text(encoding="utf-8")
        except OSError:
            pass
    return ""

def _detect_changed_files(before: dict[Path, float], after: dict[Path, float], project_root: Path) -> list[str]:
    """Detect which files changed between two mtime snapshots (new, modified, deleted)."""
    changed = []
    for path, mtime in after.items():
        if path not in before or before[path] != mtime:
            changed.append(str(path.relative_to(project_root)))
    return changed

def run_agentic_test_generate(
    prompt_file: Path | str,
    code_file: Path | str,
    output_test_file: Path | str,
    *,
    verbose: bool = False,
    quiet: bool = False
) -> tuple[str, float, str, bool, str]:
    """
    Agentic test generation for non-Python languages.
    
    Returns:
        (generated_content, cost, model_name, success, error_message)
    """
    prompt_path = Path(prompt_file).resolve()
    code_path = Path(code_file).resolve()
    test_path = Path(output_test_file).resolve()
    
    # Assume project root is the parent directory of the code file for this context
    # Adjust as needed if a specific project root is provided
    project_root = code_path.parent
    while project_root.parent != project_root:
        if (project_root / ".git").exists():
            break
        project_root = project_root.parent
    if not (project_root / ".git").exists():
        project_root = code_path.parent

    try:
        prompt_content = prompt_path.read_text(encoding="utf-8")
        code_content = code_path.read_text(encoding="utf-8")
    except OSError as e:
        error_msg = f"Failed to read input files: {e}"
        if not quiet:
            console.print(f"[bold red]{error_msg}[/bold red]")
        return "", 0.0, "unknown", False, error_msg

    template = load_prompt_template("agentic_test_generate_LLM")
    if not template:
        return "", 0.0, "unknown", False, "Prompt template 'agentic_test_generate_LLM' not found"

    full_prompt = template.format(
        prompt_path=str(prompt_path),
        code_path=str(code_path),
        test_path=str(test_path),
        project_root=str(project_root),
        prompt_content=prompt_content,
        code_content=code_content,
    )

    before_mtimes = _get_file_mtimes(project_root)

    # 1. Single-pass agentic execution (max_retries=0)
    agent_success, agent_output, cost, provider = run_agentic_task(
        instruction=full_prompt,
        cwd=project_root,
        verbose=verbose,
        max_retries=0,
    )
    
    model_name = f"agentic-{provider}"
    
    after_mtimes = _get_file_mtimes(project_root)
    changed_files = _detect_changed_files(before_mtimes, after_mtimes, project_root)

    # Parse JSON from agent output
    json_data = _extract_json_from_text(agent_output)
    error_message = ""
    is_success = agent_success

    if json_data:
        is_success = json_data.get("success", agent_success)
        if not is_success:
            error_message = json_data.get("message", "Agent reported failure without message")
    elif not agent_success:
        error_message = agent_output.strip() or "Agent execution failed"

    # If expected output file doesn't exist, check changed_files
    actual_test_path = test_path
    if not actual_test_path.exists():
        for changed_file in changed_files:
            lower_name = changed_file.lower()
            if "test" in lower_name or "spec" in lower_name:
                possible_path = project_root / changed_file
                if possible_path.exists():
                    actual_test_path = possible_path
                    if verbose:
                        console.print(f"[yellow]Test file found at alternative path: {actual_test_path}[/yellow]")
                    break

    generated_content = _read_generated_test_file(actual_test_path)
    
    if not generated_content:
        error_message = error_message or "No test file was generated."
        is_success = False

    return generated_content, cost, model_name, is_success, error_message