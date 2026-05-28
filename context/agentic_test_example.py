"""Example showing how to use run_agentic_test for GitHub issue-based test generation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the project root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdd.agentic_test import run_agentic_test


def mock_subprocess_run(args, **kwargs):
    """Mock subprocess.run to simulate GitHub CLI (gh) and Git clone operations."""
    if "gh" in args and "api" in args:
        # Check comments FIRST because comments URL also contains "issues"
        if "comments" in args[-1]:
            comments_data = [
                {
                    "user": {"login": "commenter1"},
                    "body": "More context on the login bug"
                }
            ]
            return MagicMock(returncode=0, stdout=json.dumps(comments_data), stderr="")
        elif "issues" in args[-1]:
            issue_data = {
                "title": "Test Issue",
                "body": "Fix the login bug",
                "user": {"login": "tester"},
                "comments_url": "https://api.github.com/repos/example/repo/issues/456/comments",
                "labels": [{"name": "bug"}],
                "state": "open"
            }
            return MagicMock(returncode=0, stdout=json.dumps(issue_data), stderr="")
    elif "git" in args and "clone" in args:
        return MagicMock(returncode=0, stdout="", stderr="")
    
    return MagicMock(returncode=0, stdout="", stderr="")


def main() -> None:
    """Demonstrate the agentic test workflow with a mocked GitHub issue.

    Inputs:
        issue_url (str): The URL of the GitHub issue to fetch.
        verbose (bool): Whether to enable verbose logging.
        quiet (bool): Whether to suppress standard logging output.
        timeout_adder (float): Additional timeout in seconds to add to each step.
        use_github_state (bool): Whether to load/save state from GitHub comments.

    Outputs (Tuple):
        success (bool): True if the test generation workflow succeeded, False otherwise.
        message (str): Explanatory message of the outcome.
        total_cost (float): Total LLM API cost in USD.
        model_used (str): The main model/provider used during generation.
        changed_files (List[str]): List of files created or modified by the generator.
    """

    # Example GitHub issue URL (test request)
    issue_url = "https://github.com/example/repo/issues/456"

    print(f"Running agentic test workflow for: {issue_url}")
    print("-" * 60)

    # Mock the external dependencies so that the example runs standalone and doesn't
    # require any GitHub API access, gh CLI installed, or a real git repository cloning.
    with patch("pdd.agentic_test.run_agentic_test_orchestrator") as mock_orchestrator, \
         patch("pdd.agentic_test.shutil.which", return_value="gh"), \
         patch("pdd.agentic_test.subprocess.run", side_effect=mock_subprocess_run):

        # Simulate successful 9-step workflow
        mock_orchestrator.return_value = (
            True,  # success
            "Tests generated and PR created.",  # message
            2.50,  # total_cost across all steps in USD
            "anthropic",  # model/provider used
            ["tests/e2e/test_login.spec.ts", "tests/e2e/test_dashboard.spec.ts"]  # changed_files
        )

        # --- EXECUTE THE MODULE ---
        success, message, cost, model, changed_files = run_agentic_test(
            issue_url=issue_url,
            verbose=True,
            quiet=False,
            timeout_adder=0.0,
            use_github_state=True
        )

    # Output the results
    print()
    print("--- Result Summary ---")
    print(f"Success       : {success}")
    print(f"Model Used    : {model}")
    print(f"Cost          : ${cost:.2f}")
    print(f"Changed Files : {changed_files}")
    print("-" * 30)
    print(f"Message       : {message}")
    print()
    print("Tests generated in worktree. PR created and linked to issue.")


if __name__ == "__main__":
    main()