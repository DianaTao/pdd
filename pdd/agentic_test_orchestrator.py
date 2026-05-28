"""
Agentic Test Orchestrator

Manages the 18-step "issue-to-test" automated test generation workflow.
Handles workspace isolation, context propagation, conditional looping, and resilience.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console

from pdd.agentic_common import (
    clear_agentic_progress,
    clear_workflow_state,
    detect_control_token,
    load_workflow_state,
    run_agentic_task,
    save_workflow_state,
    set_agentic_progress,
    substitute_template_variables,
    validate_cached_state,
)
from pdd.load_prompt_template import load_prompt_template

console = Console()

# 1. Timeouts Configuration
TEST_STEP_TIMEOUTS: Dict[int | float, float] = {
    1: 240.0,
    2: 240.0,
    3: 240.0,
    4: 240.0,
    5: 240.0,
    5.5: 400.0,
    6: 240.0,
    7: 240.0,
    8: 1800.0,
    9: 240.0,
    10: 240.0,
    11: 240.0,
    12: 1000.0,
    13: 240.0,
    14: 240.0,
    15: 240.0,
    16: 240.0,
    17: 240.0,
}

# 2. Git & Workspace Helpers
def _get_git_root(cwd: Path) -> Path:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, check=True
        )
        return Path(res.stdout.strip())
    except subprocess.CalledProcessError:
        return cwd

def _worktree_exists(git_root: Path, branch_name: str) -> bool:
    res = subprocess.run(["git", "worktree", "list"], cwd=git_root, capture_output=True, text=True)
    return branch_name in res.stdout

def _setup_worktree(git_root: Path, issue_number: int) -> Tuple[Optional[Path], Optional[str]]:
    branch_name = f"test/issue-{issue_number}"
    worktree_path = git_root.parent / f"wt-{branch_name.replace('/', '-')}"
    
    try:
        if _worktree_exists(git_root, branch_name) or worktree_path.exists():
            console.print(f"[yellow]Cleaning up existing worktree for {branch_name}[/yellow]")
            subprocess.run(["git", "worktree", "remove", "-f", str(worktree_path)], cwd=git_root, capture_output=True)
            subprocess.run(["git", "branch", "-D", branch_name], cwd=git_root, capture_output=True)
        
        res = subprocess.run(["git", "worktree", "add", "-b", branch_name, str(worktree_path)], cwd=git_root, capture_output=True, text=True)
        if res.returncode != 0:
            return None, res.stderr.strip() or f"git worktree add failed with exit code {res.returncode}"
            
        return worktree_path, None
    except Exception as e:
        return None, str(e)

def _detect_ci_cwd(worktree_root: Path, changed_files: List[str]) -> Path:
    """Find the project root for sub-projects within a mono-repo."""
    if not changed_files:
        return worktree_root
        
    for file_path in changed_files:
        full_path = worktree_root / file_path
        current = full_path.parent
        while current != worktree_root.parent and current != worktree_root:
            if (current / ".pddrc").exists() or (current / "pytest.ini").exists():
                return current
            current = current.parent
    return worktree_root

def _get_state_dir(cwd: Path) -> Path:
    root = _get_git_root(cwd) or cwd
    return root / ".pdd" / "test-generation-state"

# 3. Parsing Logic
def _parse_tags(output: str, tag: str) -> List[str]:
    if not output:
        return []
    
    # 1. Match XML tags
    xml_pattern = rf"<{tag}>(.*?)</{tag}>"
    xml_match = re.search(xml_pattern, output, re.DOTALL | re.IGNORECASE)
    if xml_match:
        content = xml_match.group(1).strip()
    else:
        # 2. Match colon format: FILES_CREATED: a.py, b.py
        lines = output.splitlines()
        content = ""
        for line in lines:
            line_strip = line.strip()
            idx = line_strip.upper().find(f"{tag.upper()}:")
            if idx != -1:
                content = line_strip[idx + len(tag) + 1:].strip()
                break
        else:
            return []
            
    if content.lower() in ("none", "n/a", ""):
        return []
        
    files = []
    for part in re.split(r'[\n,]', content):
        part = part.strip()
        while part and part[0] in "-*•":
            part = part[1:].lstrip()
        part = part.strip("*`").strip()
        if part:
            files.append(part)
    return files

def _check_hard_stop(step_num: int | float, output: str) -> Optional[str]:
    if not output:
        return None
        
    output_lower = output.lower()
    stop_match = re.search(r'STOP_CONDITION:\s*(.+)', output, re.IGNORECASE)
    
    if step_num == 1:
        if "duplicate of #" in output_lower:
            return "duplicate of #"
        if stop_match:
            return stop_match.group(1).strip()
        return None
        
    if step_num == 3:
        # Step 3 requires STOP_CONDITION tag, no substring fallback!
        if stop_match:
            return stop_match.group(1).strip()
        return None
        
    if step_num == 5:
        if "plan_blocked" in output_lower:
            return "plan_blocked"
        if stop_match:
            return stop_match.group(1).strip()
        return None

    # Universal fallback for any other step
    if stop_match:
        return stop_match.group(1).strip()
        
    return None

# Core Orchestrator Entry Point
def run_agentic_test_orchestrator(
    issue_url: str,
    issue_content: str,
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    issue_author: str,
    issue_title: str,
    cwd: Path,
    verbose: bool = False,
    quiet: bool = False,
    timeout_adder: float = 0.0,
    use_github_state: bool = False,
) -> Tuple[bool, str, float, str, List[str]]:
    """
    Executes the 18-step agentic workflow to generate tests from an issue.
    """
    clear_agentic_progress()
    
    if not quiet:
        console.print(f"[bold blue]Starting Agentic Test Orchestrator for Issue #{issue_number}[/bold blue]")
        
    git_root = _get_git_root(cwd) or cwd
    total_cost = 0.0
    model_used = "unknown"
    changed_files: List[str] = []
    
    # State Management: Load
    state_dir = _get_state_dir(cwd)
    state, comment_id = load_workflow_state(
        cwd, issue_number, "test_generation", state_dir, repo_owner, repo_name, use_github_state
    )
    
    if state:
        last_completed_step = state.get("last_completed_step", 0)
        step_outputs = state.get("step_outputs", {})
        total_cost = state.get("total_cost", 0.0)
        model_used = state.get("model_used", "unknown")
        # Validate cached state to handle Issue #467 / Issue #784
        last_completed_step = validate_cached_state(
            last_completed_step=last_completed_step,
            step_outputs=step_outputs,
            quiet=quiet
        )
        if not quiet:
            console.print(f"[green]Resuming from state: Step {last_completed_step}[/green]")
    else:
        step_outputs = {}
        last_completed_step = 0
        
    # Setup worktree
    worktree_path, error_msg = _setup_worktree(git_root, issue_number)
    if error_msg or not worktree_path:
        return False, f"Failed to create worktree: {error_msg}", total_cost, model_used, changed_files
        
    likely_ci_cwd = worktree_path
    
    # Recalculate context & likely_ci_cwd from cached step 12 / 15 outputs on resume
    if "12" in step_outputs:
        s12_files = _parse_tags(step_outputs["12"], "FILES_CREATED") + _parse_tags(step_outputs["12"], "FILES_MODIFIED")
        if s12_files:
            likely_ci_cwd = _detect_ci_cwd(worktree_path, s12_files)
            changed_files.extend(s12_files)
    if "15" in step_outputs:
        s15_files = _parse_tags(step_outputs["15"], "FILES_CREATED") + _parse_tags(step_outputs["15"], "FILES_MODIFIED")
        if s15_files:
            likely_ci_cwd = _detect_ci_cwd(worktree_path, s15_files)
            changed_files.extend(s15_files)
            
    # Deduplicate changed_files
    seen = set()
    changed_files = [f for f in changed_files if not (f in seen or seen.add(f))]
    
    # Context initialization
    context = {
        "issue_url": issue_url,
        "issue_content": issue_content,
        "repo_owner": repo_owner,
        "repo_name": repo_name,
        "issue_number": str(issue_number),
        "issue_author": issue_author,
        "issue_title": issue_title,
        "likely_ci_cwd": str(likely_ci_cwd),
        "frontend_type": "",
        "target_url": "",
    }
    
    # Populate context with previous step outputs
    for s_key, s_out in step_outputs.items():
        context[f"step{s_key}_output"] = s_out
        if s_key == "5.5":
            context["step5b_output"] = s_out
            
    # Extract frontend_type and target_url from Step 4 if available
    s4_out = step_outputs.get("4", "")
    t_match = re.search(r'TEST_TYPE:\s*([^\s\n]+)', s4_out, re.IGNORECASE)
    if t_match:
        context["frontend_type"] = t_match.group(1).strip()
    u_match = re.search(r'TARGET_URL:\s*([^\s\n]+)', s4_out, re.IGNORECASE)
    if u_match:
        context["target_url"] = u_match.group(1).strip()
        
    frontend_type = context["frontend_type"]
    
    steps = [1, 2, 3, 4, 5, 5.5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    idx = 0
    loop_count = 0
    
    while idx < len(steps):
        step = steps[idx]
        
        if step <= last_completed_step:
            idx += 1
            continue
            
        if not quiet:
            console.print(f"[bold cyan]--- Executing Step {step} ---[/bold cyan]")
            
        # Gating steps 6-11 for web tests
        if 6 <= step <= 11:
            if "web" not in frontend_type.lower():
                if not quiet:
                    console.print(f"[dim]Skipping Step {step} (Not a web test)[/dim]")
                last_completed_step = step
                idx += 1
                continue
                
        # Step 16 skip logic
        if step == 16:
            s15_files = _parse_tags(step_outputs.get("15", ""), "FILES_CREATED")
            if not s15_files:
                if not quiet:
                    console.print("[dim]Skipping Step 16 (No new files created in Step 15)[/dim]")
                last_completed_step = step
                idx += 1
                continue
                
        # Update progress
        set_agentic_progress(
            workflow="test_generation",
            current_step=int(step) if isinstance(step, (int, float)) and step == int(step) else step,
            total_steps=18,
            step_name=f"test_step_{str(step).replace('.', '_')}",
            completed_steps=[int(s) for s in step_outputs.keys() if s.isdigit()]
        )
        
        # Load template
        prompt_template = load_prompt_template(f"test_step_{str(step).replace('.', '_')}")
        if prompt_template is None:
            # Missing template returns failure gracefully
            success = False
            output = ""
            cost = 0.0
            provider = "unknown"
        else:
            # Update likely_ci_cwd in context
            context["likely_ci_cwd"] = str(likely_ci_cwd)
            # Format prompt
            full_prompt = substitute_template_variables(prompt_template, context)
            
            # Determine timeout
            timeout = TEST_STEP_TIMEOUTS.get(step, TEST_STEP_TIMEOUTS.get(int(step), 240.0)) + timeout_adder
            
            # Check PDD_CLOUD_RUN
            use_cloud_run = os.environ.get("PDD_CLOUD_RUN") == "true" or os.environ.get("PDD_CLOUD_RUN") == "1"
            if use_cloud_run and step == 8:
                results_path = likely_ci_cwd / "cloud_run_results.json"
                if not quiet:
                    console.print(f"[cyan]Cloud Run enabled. Polling for results at {results_path}...[/cyan]")
                found = False
                for _ in range(10):
                    if results_path.exists():
                        try:
                            with open(results_path, "r") as f:
                                poll_data = json.load(f)
                            output = poll_data.get("output", "Cloud run completed.")
                            success = poll_data.get("success", True)
                            cost = poll_data.get("cost", 0.0)
                            provider = poll_data.get("provider", "cloud")
                            found = True
                            break
                        except Exception:
                            pass
                    time.sleep(1)
                if not found:
                    success, output, cost, provider = run_agentic_task(
                        instruction=full_prompt,
                        cwd=likely_ci_cwd,
                        verbose=verbose,
                        quiet=quiet,
                        label=f"step{step}",
                        timeout=timeout,
                        use_playwright=(step == 8)
                    )
            else:
                success, output, cost, provider = run_agentic_task(
                    instruction=full_prompt,
                    cwd=likely_ci_cwd,
                    verbose=verbose,
                    quiet=quiet,
                    label=f"step{step}",
                    timeout=timeout,
                    use_playwright=(step == 8)
                )
                
        total_cost += cost
        model_used = provider
        
        # Save output
        step_outputs[str(step)] = output
        context[f"step{str(step)}_output"] = output
        if step == 5.5:
            context["step5b_output"] = output
            
        # Parse tags/extracts on success/failure
        # If step 4, parse frontend_type and target_url
        if step == 4:
            t_match = re.search(r'TEST_TYPE:\s*([^\s\n]+)', output, re.IGNORECASE)
            if t_match:
                context["frontend_type"] = t_match.group(1).strip()
                frontend_type = context["frontend_type"]
            u_match = re.search(r'TARGET_URL:\s*([^\s\n]+)', output, re.IGNORECASE)
            if u_match:
                context["target_url"] = u_match.group(1).strip()
                
        # Parse changed files from step 12 and 15
        if step == 12 or step == 15:
            files = _parse_tags(output, "FILES_CREATED") + _parse_tags(output, "FILES_MODIFIED")
            if files:
                likely_ci_cwd = _detect_ci_cwd(worktree_path, files)
                changed_files.extend(files)
                # Deduplicate changed_files
                seen_f = set()
                changed_files = [f for f in changed_files if not (f in seen_f or seen_f.add(f))]
                
        # If Step 12 produces no new files, stop
        if step == 12:
            s12_files = _parse_tags(output, "FILES_CREATED") + _parse_tags(output, "FILES_MODIFIED")
            if not s12_files:
                return False, "Stopped at step 12: No test file created or modified.", total_cost, model_used, changed_files
                
        # Handle hard stop conditions
        stop_reason = _check_hard_stop(step, output)
        if stop_reason:
            if step == 3:
                # Clarification step 3 saves previous step so step 3 re-runs on resume (Bug #784)
                save_workflow_state(
                    cwd,
                    issue_number,
                    "test_generation",
                    {
                        "last_completed_step": 2,
                        "step_outputs": step_outputs,
                        "total_cost": total_cost,
                        "model_used": model_used,
                        "worktree_path": str(worktree_path)
                    },
                    state_dir,
                    repo_owner,
                    repo_name,
                    use_github_state,
                    comment_id
                )
                return False, f"Stopped at step 3: {stop_reason}", total_cost, model_used, changed_files
            else:
                # Other steps just stop
                if step == 5:
                    return False, f"Stopped at step 5: Plan is not achievable due to: {stop_reason}", total_cost, model_used, changed_files
                return False, f"Stopped at step {step}: {stop_reason}", total_cost, model_used, changed_files
                
        # Parse changed files from any other step to keep changed_files list complete (e.g. step 14)
        if step in (13, 14, 16):
            files = _parse_tags(output, "FILES_CREATED") + _parse_tags(output, "FILES_MODIFIED")
            if files:
                changed_files.extend(files)
                seen_f = set()
                changed_files = [f for f in changed_files if not (f in seen_f or seen_f.add(f))]
                
        # Loop steps 8-11 back if CONTINUE_CYCLE is found
        if step == 11 and "web" in frontend_type.lower():
            loop_count += 1
            if loop_count < 3:
                if detect_control_token(output, "CONTINUE_CYCLE"):
                    if not quiet:
                        console.print("[yellow]Looping back to Step 8 for web testing...[/yellow]")
                    # Find index of step 8
                    idx = steps.index(8)
                    last_completed_step = 7
                    # Save state for resumption inside the loop
                    comment_id = save_workflow_state(
                        cwd,
                        issue_number,
                        "test_generation",
                        {
                            "last_completed_step": last_completed_step,
                            "step_outputs": step_outputs,
                            "total_cost": total_cost,
                            "model_used": model_used,
                            "worktree_path": str(worktree_path)
                        },
                        state_dir,
                        repo_owner,
                        repo_name,
                        use_github_state,
                        comment_id
                    )
                    continue
                    
        # Update last_completed_step
        last_completed_step = step
        
        # Save workflow state
        comment_id = save_workflow_state(
            cwd,
            issue_number,
            "test_generation",
            {
                "last_completed_step": last_completed_step,
                "step_outputs": step_outputs,
                "total_cost": total_cost,
                "model_used": model_used,
                "worktree_path": str(worktree_path)
            },
            state_dir,
            repo_owner,
            repo_name,
            use_github_state,
            comment_id
        )
        
        idx += 1
        
    # Clear state on successful completion
    clear_workflow_state(
        cwd,
        issue_number,
        "test_generation",
        state_dir,
        repo_owner,
        repo_name,
        use_github_state
    )
    clear_agentic_progress()
    
    # Return success and last step output or similar message
    msg = step_outputs.get("17", "Workflow completed successfully.")
    return True, msg, total_cost, model_used, changed_files
