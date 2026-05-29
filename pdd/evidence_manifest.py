# pdd/evidence_manifest.py
from __future__ import annotations

import os
import json
import hashlib
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _hash_file(filepath: Path) -> str:
    """Calculate SHA256 of a file."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
    except Exception:
        return ""
    return hasher.hexdigest()


def _preprocessed_expanded_sha256(prompt_text: str, project_root: Path) -> Optional[str]:
    """Calculate the hash of the preprocessed prompt.

    Recursively resolves includes and returns SHA256 of the resulting string.
    Returns None for dynamic prompts (containing <shell> or <web> tags).
    """
    from pdd.preprocess import preprocess
    
    # Check for non-deterministic tags
    if "<shell>" in prompt_text or "<web>" in prompt_text:
        return None
        
    previous = os.getcwd()
    os.chdir(project_root)
    try:
        # Match test expectations: recursive=True, double_curly_brackets=False
        expanded = preprocess(prompt_text, recursive=True, double_curly_brackets=False)
        return hashlib.sha256(expanded.encode("utf-8")).hexdigest()
    finally:
        os.chdir(previous)


def validation_from_sync(
    sync_result: Dict[str, Any],
    *,
    skip_tests: bool,
    skip_verify: bool,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Map real sync outcomes to a validation dictionary.
    Never claim `passed` unless the invoking command established that state.
    """
    if dry_run:
        return {
            "detect_stories": "not_available",
            "unit_tests": "not_available",
            "verify": "not_available",
            "dry_run": True
        }

    results = sync_result.get("results_by_language", {}).get("python", {})
    ops = results.get("operations_completed", [])
    success = results.get("success", False)

    validation = {
        "detect_stories": "not_applicable",
        "unit_tests": "not_applicable",
        "verify": "not_applicable"
    }

    if not skip_tests and "test" in ops:
        validation["unit_tests"] = "passed" if success else "failed"
    if not skip_verify and "verify" in ops:
        validation["verify"] = "passed" if success else "failed"
            
    return validation


def resolve_generate_output_paths(prompt_file: Path, quiet: bool = False) -> List[str]:
    """Resolve the expected output paths for a generate command."""
    from pdd.construct_paths import construct_paths
    
    input_files = {"prompt_file": str(prompt_file)}
    
    _, _, output_paths, _ = construct_paths(
        input_file_paths=input_files,
        force=True,
        quiet=quiet,
        command="generate",
        command_options={}
    )
    
    return list(output_paths.values())


def _collect_includes_recursive(
    text: str, 
    base_dir: Path, 
    project_root: Path, 
    seen_resolved: set[str], 
    collected_rel_paths: set[str]
) -> None:
    """Recursively collect all includes from a prompt string."""
    from pdd.preprocess import compute_user_intent_paths
    
    intent_paths = compute_user_intent_paths(text)
    for p_str in intent_paths:
        # Resolution logic similar to pdd.preprocess
        candidates = [
            base_dir / p_str,
            project_root / p_str,
            Path(p_str)
        ]
        
        resolved_path = None
        for cand in candidates:
            if cand.exists() and cand.is_file():
                resolved_path = cand.resolve()
                break
        
        if resolved_path and str(resolved_path) not in seen_resolved:
            seen_resolved.add(str(resolved_path))
            try:
                rel_path = str(resolved_path.relative_to(project_root))
            except ValueError:
                rel_path = str(resolved_path)
            
            collected_rel_paths.add(rel_path)
            
            # Recurse
            try:
                child_content = resolved_path.read_text(encoding="utf-8")
                _collect_includes_recursive(
                    child_content, 
                    resolved_path.parent, 
                    project_root, 
                    seen_resolved, 
                    collected_rel_paths
                )
            except Exception:
                pass


def write_evidence_manifest(
    command: str,
    prompt_file: Path,
    output_files: Optional[List[Path]] = None,
    model: Optional[str] = None,
    cost_usd: float = 0.0,
    temperature: float = 0.0,
    project_root: Optional[Path] = None,
    validation: Optional[Dict[str, Any]] = None,
    logs: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Writes optional per-run JSON evidence manifests for supported PDD commands.
    Writes schema v1 JSON under .pdd/evidence/
    """
    from rich.console import Console
    console = Console()

    if project_root is None:
        project_root = Path.cwd()

    try:
        evidence_dir = project_root / ".pdd" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Read prompt
        prompt_text = prompt_file.read_text(encoding="utf-8")
        prompt_hash = _hash_file(prompt_file)
        
        # Expanded hash
        expanded_sha256 = _preprocessed_expanded_sha256(prompt_text, project_root)
        uses_nondeterministic_tags = "<shell>" in prompt_text or "<web>" in prompt_text
        
        # Resolve includes recursively
        seen_resolved = {str(prompt_file.resolve())}
        collected_rel_paths = set()
        _collect_includes_recursive(
            prompt_text, 
            prompt_file.parent, 
            project_root, 
            seen_resolved, 
            collected_rel_paths
        )
        
        includes = []
        for rel_path in sorted(collected_rel_paths):
            p = project_root / rel_path
            if p.exists() and p.is_file():
                includes.append({
                    "path": rel_path,
                    "sha256": _hash_file(p)
                })
        
        # Outputs
        outputs = []
        if output_files:
            for p in output_files:
                if isinstance(p, str):
                    p = Path(p)
                if p.exists():
                    try:
                        rel_path = str(p.relative_to(project_root))
                    except ValueError:
                        rel_path = str(p)
                    outputs.append({
                        "path": rel_path,
                        "sha256": _hash_file(p)
                    })

        # Manifest structure matching schema
        final_validation = {
            "detect_stories": "not_applicable",
            "unit_tests": "not_applicable",
            "verify": "not_applicable"
        }
        if validation:
            final_validation.update(validation)

        final_logs = {
            "core_dump": None,
            "verify_results": None,
            "cost_csv": None
        }
        if logs:
            final_logs.update(logs)

        manifest = {
            "schema_version": 1,
            "run": {
                "id": prompt_hash[:8], # Simple ID
                "command": command,
                "pdd_version": "unknown",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            },
            "prompt": {
                "path": str(prompt_file.relative_to(project_root)),
                "sha256": prompt_hash,
                "expanded_sha256": expanded_sha256,
                "uses_nondeterministic_tags": uses_nondeterministic_tags
            },
            "context": {
                "includes": includes,
                "web_snapshots": [],
                "shell_snapshots": []
            },
            "generation": {
                "model": model,
                "temperature": temperature,
                "cost_usd": cost_usd,
                "grounding_examples": []
            },
            "outputs": outputs,
            "contracts": {
                "status": "not_applicable",
                "rules": {}
            },
            "validation": final_validation,
            "logs": final_logs
        }
        
        # Contract enrichment
        try:
            import coverage_contracts
            if hasattr(coverage_contracts, "get_active_contracts"):
                manifest["contracts"]["status"] = "available"
                manifest["contracts"]["rules"] = coverage_contracts.get_active_contracts()
        except ImportError:
            pass

        from pdd.construct_paths import _strip_language_suffix
        basename = _strip_language_suffix(prompt_file)
        
        devunits_dir = evidence_dir / "devunits"
        devunits_dir.mkdir(parents=True, exist_ok=True)
        
        latest_file = devunits_dir / f"{basename}.latest.json"
        
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest_file = evidence_dir / f"manifest_{timestamp_str}_{prompt_hash[:8]}.json"

        content = json.dumps(manifest, indent=2)
        manifest_file.write_text(content, encoding="utf-8")
        latest_file.write_text(content, encoding="utf-8")
        
        return manifest_file

    except Exception as e:
        console.print(f"[red]Error writing evidence manifest: {e}[/red]")
        # Return a dummy path if something goes wrong
        return Path("/tmp/error_manifest.json")

def resolve_generate_output_paths(prompt_file: Path, quiet: bool = False) -> List[str]:
    """Resolve the expected output paths for a generate command."""
    from pdd.construct_paths import construct_paths
    
    input_files = {"prompt_file": str(prompt_file)}
    
    _, _, output_paths, _ = construct_paths(
        input_file_paths=input_files,
        force=True,
        quiet=quiet,
        command="generate",
        command_options={}
    )
    
    return list(output_paths.values())


def resolve_test_output_paths(prompt_file: Path, quiet: bool = False) -> List[str]:
    """Resolve the expected output paths for a test command."""
    from pdd.construct_paths import construct_paths
    
    input_files = {"prompt_file": str(prompt_file)}
    
    _, _, output_paths, _ = construct_paths(
        input_file_paths=input_files,
        force=True,
        quiet=quiet,
        command="test",
        command_options={}
    )
    
    return list(output_paths.values())
