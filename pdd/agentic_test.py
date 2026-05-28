"""
CLI entry point for the agentic test generation workflow.
Fetches a GitHub issue, extracts content and metadata describing what needs to be tested,
then invokes the orchestrator to run the 9-step test generation process (supports UI, CLI, and API tests).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from urllib.parse import urlparse

from rich.console import Console

from .agentic_test_orchestrator import run_agentic_test_orchestrator
from . import cmd_test_main
from . import DEFAULT_STRENGTH, DEFAULT_TIME

# Initialize console for rich output
console = Console()


def _check_gh_cli() -> bool:
    """Check if the GitHub CLI (gh) is installed and available."""
    return shutil.which("gh") is not None


def _parse_github_url(url: str) -> Optional[Tuple[str, str, int]]:
    """
    Parse GitHub issue URL to extract owner, repo, and issue number.
    Supported formats:
    - https://github.com/{owner}/{repo}/issues/{number}
    - https://www.github.com/{owner}/{repo}/issues/{number}
    - github.com/{owner}/{repo}/issues/{number}
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    try:
        if "issues" in path_parts:
            issues_index = path_parts.index("issues")
            if issues_index >= 2 and len(path_parts) > issues_index + 1:
                owner = path_parts[issues_index - 2]
                repo = path_parts[issues_index - 1]
                number_str = path_parts[issues_index + 1]
                return owner, repo, int(number_str)
    except ValueError:
        return None
        
    return None


def _fetch_issue_data(owner: str, repo: str, number: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Fetch issue data and comments using the GitHub CLI.
    Returns (issue_data_dict, error_message).
    """
    try:
        cmd = [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/{number}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issue_json = json.loads(result.stdout)

        labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in issue_json.get("labels", [])]
        state = issue_json.get("state", "open")

        comments_url = issue_json.get("comments_url")
        comments_text = ""
        if comments_url:
            cmd_comments = ["gh", "api", comments_url]
            res_comments = subprocess.run(cmd_comments, capture_output=True, text=True, check=False)
            if res_comments.returncode == 0:
                try:
                    comments_data = json.loads(res_comments.stdout)
                    if isinstance(comments_data, list):
                        comments_text = "\n\n--- Comments ---\n"
                        for comment in comments_data:
                            user = comment.get("user", {}).get("login", "Unknown")
                            body = comment.get("body", "")
                            comments_text += f"\nUser: {user}\n{body}\n"
                except json.JSONDecodeError:
                    pass

        meta_info = f"State: {state}\nLabels: {', '.join(labels)}\n"
        full_content = meta_info + "\n" + (issue_json.get("body") or "") + comments_text
        issue_json["full_content_with_comments"] = full_content
        
        return issue_json, None

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else str(e)
        return None, f"GitHub API call failed: {err_msg}"
    except json.JSONDecodeError:
        return None, "Failed to parse GitHub API response"
    except Exception as e:
        return None, str(e)


def _ensure_repo_context(owner: str, repo: str, cwd: Path, quiet: bool) -> Tuple[bool, str]:
    """
    Ensure we are in the correct repository.
    If the current directory is not the repo, clone it to a temp directory.
    Returns (success, path_or_error_msg).
    """
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            remote_url = res.stdout.strip()
            if f"{owner}/{repo}" in remote_url or f"{owner}:{repo}" in remote_url:
                return True, str(cwd)
    except FileNotFoundError:
        pass

    try:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"pdd_test_{repo}_"))
    except Exception as e:
        return False, f"Failed to create temp directory: {e}"

    if not quiet:
        console.print(f"[yellow]Current directory does not match {owner}/{repo}. Cloning to {temp_dir}...[/yellow]")
    
    try:
        clone_url = f"https://github.com/{owner}/{repo}.git"
        subprocess.run(["git", "clone", clone_url, "."], cwd=temp_dir, check=True, capture_output=quiet)
        return True, str(temp_dir)
    except subprocess.CalledProcessError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False, f"Failed to clone repository: {e}"


def run_agentic_test(
    issue_url: str,
    *,
    verbose: bool = False,
    quiet: bool = False,
    timeout_adder: float = 0.0,
    use_github_state: bool = True,
    manual: bool = False,
    prompt_file: Optional[str] = None,
    code_file: Optional[str] = None,
) -> Tuple[bool, str, float, str, List[str]]:
    """
    Run the agentic test generation workflow for a given GitHub issue URL.

    Args:
        issue_url: The GitHub issue URL.
        verbose: Enable verbose logging.
        quiet: Suppress standard logging.
        timeout_adder: Additional time to add to each step timeout.
        use_github_state: Whether to use GitHub issue comments for state resumption.
        manual: If True, falls back to legacy prompt-based test generation.
        prompt_file: Required if manual is True.
        code_file: Required if manual is True.

    Returns:
        A 5-tuple containing:
        - success (bool)
        - message (str)
        - total_cost (float)
        - model_used (str)
        - changed_files (List[str])
    """
    if manual:
        if not prompt_file or not code_file:
            return False, "Manual mode requires both prompt_file and code_file.", 0.0, "", []
        
        try:
            import click
            ctx = click.Context(click.Command("test"))
            ctx.obj = {"verbose": verbose, "quiet": quiet}
            
            test_code, cost, model, success, err = cmd_test_main.cmd_test_main(
                ctx=ctx,
                prompt_file=prompt_file,
                code_file=code_file,
                output=None,
                language="python",
                strength=DEFAULT_STRENGTH,
            )
            return bool(success), err or "Manual test generation completed.", cost, model, []
        except Exception as e:
            return False, f"Manual mode failed: {str(e)}", 0.0, "", []

    # 1. Check prerequisites
    if not _check_gh_cli():
        msg = "GitHub CLI (gh) not found. Please install it: https://cli.github.com/"
        if not quiet:
            console.print(f"[red]{msg}[/red]")
        return False, "gh CLI not found", 0.0, "", []

    # 2. Parse URL
    parsed = _parse_github_url(issue_url)
    if not parsed:
        msg = f"Invalid GitHub URL format: {issue_url}"
        if not quiet:
            console.print(f"[red]{msg}[/red]")
        return False, "Invalid GitHub URL", 0.0, "", []
    
    owner, repo, issue_number = parsed

    if not quiet:
        console.print(f"[blue]Fetching issue #{issue_number} from {owner}/{repo}...[/blue]")

    # 3. Fetch Issue Data
    issue_data, error = _fetch_issue_data(owner, repo, issue_number)
    if not issue_data:
        msg = f"Issue not found or API error: {error}"
        if not quiet:
            console.print(f"[red]{msg}[/red]")
        return False, f"Issue not found: {error}", 0.0, "", []

    # Extract metadata
    issue_title = issue_data.get("title", f"Issue #{issue_number}")
    issue_author = issue_data.get("user", {}).get("login", "unknown")
    issue_content = issue_data.get("full_content_with_comments", "")
    
    # Extract labels and state to satisfy Req 6
    labels = issue_data.get("labels", [])
    state = issue_data.get("state", "open")

    # 4. Setup Repository Context
    current_cwd = Path.cwd()
    is_repo, repo_path_str = _ensure_repo_context(owner, repo, current_cwd, quiet)
    
    if not is_repo:
        if not quiet:
            console.print(f"[red]{repo_path_str}[/red]")
        return False, repo_path_str, 0.0, "", []
    
    repo_path = Path(repo_path_str)

    # 5. Run Orchestrator
    try:
        return run_agentic_test_orchestrator(
            issue_url=issue_url,
            issue_content=issue_content,
            repo_owner=owner,
            repo_name=repo,
            issue_number=issue_number,
            issue_author=issue_author,
            issue_title=issue_title,
            cwd=repo_path,
            verbose=verbose,
            quiet=quiet,
            timeout_adder=timeout_adder,
            use_github_state=use_github_state
        )
    except Exception as e:
        import traceback
        if verbose:
            traceback.print_exc()
        return False, f"Orchestrator failed: {str(e)}", 0.0, "unknown", []
    finally:
        # Cleanup if we created a temp directory
        if repo_path != current_cwd and repo_path.exists():
            if not quiet:
                console.print(f"[dim]Cleaning up temporary repository at {repo_path}...[/dim]")
            try:
                shutil.rmtree(repo_path)
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]Warning: Failed to cleanup temp dir: {e}[/yellow]")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Agentic Test Generation CLI")
    parser.add_argument("--manual", action="store_true", help="Use manual prompt-based generation (legacy mode)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    parser.add_argument("--timeout-adder", type=float, default=0.0, help="Add seconds to step timeouts")
    parser.add_argument("--no-github-state", action="store_true", help="Disable GitHub state persistence")
    
    args, remaining = parser.parse_known_args()

    if args.manual:
        sys.argv = [arg for arg in sys.argv if arg != "--manual"]
        cmd_test_main.main()
        return

    if not remaining:
        console.print("[red]Error: Issue URL required[/red]")
        sys.exit(1)
    
    issue_url = remaining[0]
    
    success, msg, cost, model, files = run_agentic_test(
        issue_url=issue_url,
        verbose=args.verbose,
        quiet=args.quiet,
        timeout_adder=args.timeout_adder,
        use_github_state=not args.no_github_state
    )
    
    if not success:
        sys.exit(1)


def agentic_test_main() -> None:
    """Backward-compatible alias for CLI entry point."""
    main()


if __name__ == "__main__":
    main()