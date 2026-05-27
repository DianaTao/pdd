"""
Contract coverage: identify prompt-to-story links and report gaps.

Logic for ``pdd coverage --contracts`` which cross-references module prompts
against user stories (story__*.md) to ensure every prompt has coverage evidence.
"""
from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple

import click
from rich.console import Console
from rich.table import Table

# Regex to match pdd-story-prompts metadata in stories
STORY_METADATA_RE = re.compile(
    r"<!--\s*pdd-story-prompts:\s*(?P<prompts>.*?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)

# Regex to match prompt file references (e.g. foo.prompt)
STORY_PROMPT_REFERENCE_RE = re.compile(
    r"(?P<ref>[A-Za-z0-9_./-]+\.prompt)\b",
    flags=re.IGNORECASE,
)

# Regex to match ## Covers section in stories
STORY_COVERS_SECTION_RE = re.compile(
    r"##\s*Covers\s*\n(?P<content>.*?)(?=\n##|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Regex to match requirement obligations (e.g. R1, R2) in prompts
PROMPT_REQUIREMENT_RE = re.compile(
    r"^\s*(?P<id>R\d+):\s*(?P<desc>.*)$",
    re.MULTILINE
)

# Regex to match requirement references in tests (e.g. R1, PromptName:R1)
TEST_REQUIREMENT_REF_RE = re.compile(
    r"(?P<prompt>[A-Za-z0-9_./-]+:)?(?P<id>R\d+)\b",
    re.IGNORECASE
)

def _story_links_prompt(story_content: str, prompt_name: str) -> bool:
    """Check if a story links to a specific prompt name."""
    # 1. Check metadata
    meta_match = STORY_METADATA_RE.search(story_content)
    if meta_match:
        prompts_list = meta_match.group("prompts")
        for ref_match in STORY_PROMPT_REFERENCE_RE.finditer(prompts_list):
            ref = ref_match.group("ref")
            if ref == prompt_name or Path(ref).name == prompt_name:
                return True
    
    # 2. Check ## Covers section
    match = STORY_COVERS_SECTION_RE.search(story_content)
    if match:
        content = match.group("content")
        for ref_match in STORY_PROMPT_REFERENCE_RE.finditer(content):
            ref = ref_match.group("ref")
            if ref == prompt_name or Path(ref).name == prompt_name:
                return True
                
    return False

def scan_test_evidence(tests_dir: Path) -> Dict[Tuple[str, str], List[str]]:
    """
    Scan test files for requirement references.
    Returns a map of (prompt_name, req_id) -> [test_file_paths].
    """
    evidence: Dict[Tuple[str, str], List[str]] = {}
    
    if not tests_dir.exists():
        return evidence

    for root, _, files in os.walk(tests_dir):
        for file in files:
            if not (file.startswith("test_") and file.endswith(".py")):
                continue
            
            path = Path(root) / file
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue

            # Default prompt name from filename (e.g. test_foo.py -> foo)
            default_prompt = file[5:-3]
            if default_prompt.endswith("_test"):
                default_prompt = default_prompt[:-5]
            
            for match in TEST_REQUIREMENT_REF_RE.finditer(content):
                prompt_prefix = match.group("prompt")
                req_id = match.group("id").upper()
                
                if prompt_prefix:
                    prompt_name = prompt_prefix[:-1] # strip colon
                else:
                    prompt_name = default_prompt
                
                key = (prompt_name, req_id)
                if key not in evidence:
                    evidence[key] = []
                if str(path) not in evidence[key]:
                    evidence[key].append(str(path))
                    
    return evidence

def build_coverage(
    prompt_files: List[Path], 
    story_files: List[Path],
    test_evidence: Dict[Tuple[str, str], List[str]]
) -> Dict[str, Dict[str, List[str]]]:
    """
    Build a coverage matrix for all prompts.
    Returns a map of prompt_name -> {
        'stories': [story_paths],
        'tests': [test_paths],
        'missing_reqs': [req_ids]
    }
    """
    coverage = {}
    
    for prompt_path in prompt_files:
        prompt_name = prompt_path.name
        try:
            prompt_content = prompt_path.read_text(encoding="utf-8")
        except Exception:
            continue
            
        reqs = [m.group("id").upper() for m in PROMPT_REQUIREMENT_RE.finditer(prompt_content)]
        
        stories = []
        for story_path in story_files:
            try:
                story_content = story_path.read_text(encoding="utf-8")
                if _story_links_prompt(story_content, prompt_name):
                    stories.append(str(story_path))
            except Exception:
                continue
                
        tests = set()
        missing_reqs = []
        
        prompt_stem = prompt_path.stem
        # Also try prompt stem (without .prompt)
        prompt_variants = [prompt_name, prompt_stem]
        if "_" in prompt_stem:
            prompt_variants.append(prompt_stem.rsplit("_", 1)[0])

        for req_id in reqs:
            req_covered = False
            for variant in prompt_variants:
                if (variant, req_id) in test_evidence:
                    tests.update(test_evidence[(variant, req_id)])
                    req_covered = True
            
            if not req_covered:
                missing_reqs.append(req_id)
        
        coverage[prompt_name] = {
            "stories": stories,
            "tests": sorted(list(tests)),
            "missing_reqs": missing_reqs,
            "has_reqs": len(reqs) > 0
        }
        
    return coverage

def run_coverage_contracts_cli(
    prompts_dir: Path,
    stories_dir: Path,
    tests_dir: Optional[Path] = None,
    quiet: bool = False,
    verbose: bool = False,
) -> None:
    """Execute the contract coverage check and report to console."""
    console = Console()
    
    prompt_files = list(prompts_dir.glob("*.prompt"))
    story_files = list(stories_dir.glob("story__*.md"))
    
    if not prompt_files:
        console.print("[yellow]No prompt files found.[/yellow]")
        return

    test_evidence = {}
    if tests_dir:
        test_evidence = scan_test_evidence(tests_dir)

    coverage = build_coverage(prompt_files, story_files, test_evidence)
    
    table = Table(title="PDD Contract Coverage Matrix")
    table.add_column("Prompt", style="cyan")
    table.add_column("Stories", style="green")
    table.add_column("Tests", style="blue")
    table.add_column("Status", style="bold")

    covered_count = 0
    for prompt_name, data in sorted(coverage.items()):
        stories = data["stories"]
        tests = data["tests"]
        missing = data["missing_reqs"]
        
        story_links = ", ".join([Path(s).name for s in stories]) if stories else "[red]None[/red]"
        test_links = ", ".join([Path(t).name for t in tests]) if tests else "[red]None[/red]"
        
        if data["has_reqs"]:
            if not missing:
                status = "[green]COVERED[/green]"
                covered_count += 1
            else:
                status = f"[yellow]MISSING {', '.join(missing)}[/yellow]"
        else:
            if stories:
                status = "[green]LINKED[/green]"
                covered_count += 1
            else:
                status = "[red]NO LINK[/red]"

        table.add_row(prompt_name, story_links, test_links, status)

    if not quiet:
        console.print(table)
        
        total = len(coverage)
        percent = (covered_count / total * 100) if total > 0 else 0
        console.print(f"\n[bold]Overall Coverage: {covered_count}/{total} prompts ({percent:.1f}%)[/bold]")

    # Exit with code 1 if any prompt is missing coverage
    # Definition of missing coverage: 
    # - If has requirements, any requirement missing tests.
    # - If no requirements, no stories linked.
    has_gaps = False
    for data in coverage.values():
        if data["has_reqs"]:
            if data["missing_reqs"]:
                has_gaps = True
                break
        else:
            if not data["stories"]:
                has_gaps = True
                break
                
    if has_gaps:
        raise click.exceptions.Exit(1)
