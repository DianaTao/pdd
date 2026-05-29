"""PDD - Prompt Driven Development"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _metadata_version
import os
import subprocess
from pathlib import Path

# --- Constants & Public API Exports ---

# Strength parameter used for LLM extraction across the codebase
# Used in postprocessing, XML tagging, code generation, and other extraction
# operations. The module should have a large context window and be affordable.
EXTRACTION_STRENGTH = 0.5

DEFAULT_STRENGTH = float(os.getenv("PDD_STRENGTH_DEFAULT", "1.0"))

DEFAULT_TEMPERATURE = 0.0

DEFAULT_TIME = 0.25

# Public OAuth credentials for cloud mode
# These are safe to embed as they are public client identifiers:
# - Firebase API keys are designed to be public (client-side)
# - GitHub OAuth Client IDs are public (the secret stays server-side)
# Users still need to authenticate via GitHub OAuth to use cloud features.
_DEFAULT_FIREBASE_API_KEY = "AIzaSyC0w2jwRR82ZFgQs_YXJoEBqnnTH71X6BE"
_DEFAULT_GITHUB_CLIENT_ID = "Ov23liJ4eSm0y5W1L20u"

# --- Imports (noqa: E402 used to avoid circular imports while allowing constants at top) ---

from .agentic_common import (  # noqa: E402
    get_agent_provider_preference,
    get_job_deadline,
    Pricing,
    get_available_agents,
    run_agentic_task,
    github_save_state,
    github_load_state,
    github_clear_state,
    validate_cached_state,
    load_workflow_state,
    save_workflow_state,
    clear_workflow_state,
    post_step_comment,
    substitute_template_variables,
    post_pr_comment,
    post_final_comment,
    _extract_step_report,
    _sanitize_comment_body
)
from .agentic_test_orchestrator import run_agentic_test_orchestrator  # noqa: E402
from .architecture_sync_helper import filepath_to_prompt_filename  # noqa: E402
from .agentic_e2e_fix_orchestrator import run_agentic_e2e_fix_orchestrator  # noqa: E402
from .ci_validation import detect_ci_system, post_ci_failure_comment, run_ci_validation_loop  # noqa: E402
from .agentic_e2e_fix import run_agentic_e2e_fix  # noqa: E402
from .agentic_bug_orchestrator import run_agentic_bug_orchestrator  # noqa: E402
from .agentic_update import run_agentic_update  # noqa: E402
from .update_main import (  # noqa: E402
    resolve_prompt_code_pair,
    find_and_resolve_all_pairs,
    get_git_changed_files,
    derive_basename_and_language,
    is_code_changed,
    update_file_pair,
    update_main
)
from .ci_drift_heal import DriftInfo, HealResult, detect_drift, heal_module, commit_and_push, main as ci_drift_heal_main  # noqa: E402
from .agentic_change_orchestrator import run_agentic_change_orchestrator  # noqa: E402
from .agentic_common_worktree import (  # noqa: E402
    get_git_root,
    worktree_exists,
    branch_exists,
    remove_worktree,
    delete_branch,
    resolve_main_ref,
    setup_worktree,
    get_modified_and_untracked,
    check_target_file_unchanged,
    revert_out_of_scope_changes_with_dirs,
    extract_block_marker
)
from .get_lint_commands import LintCommand, get_lint_commands  # noqa: E402
from .split_main import split_main  # noqa: E402
from .split_validation import ValidationFailure, ValidationResult, validate_extraction  # noqa: E402
from .agentic_split_orchestrator import (  # noqa: E402
    run_agentic_split_orchestrator,
    Diagnosis,
    ModuleInvestigation,
    TestOwnership,
    PromptMetadata,
    Child,
    ParentChanges,
    SplitPlan,
    SplitOption,
    OptionsConsidered,
    QualitativeAssessment
)
from .agentic_split import run_agentic_split  # noqa: E402
from .ci_detect_changed_modules import main as ci_detect_changed_modules_main  # noqa: E402
from .agentic_architecture_orchestrator import (  # noqa: E402
    load_workflow_state as arch_load_workflow_state,
    save_workflow_state as arch_save_workflow_state,
    clear_workflow_state as arch_clear_workflow_state,
    run_agentic_architecture_orchestrator
)


# --- Helper functions ---

def _derive_git_aligned_version() -> str | None:
    """Return tag-aligned development version for the current git checkout."""
    repo_root = Path(__file__).resolve().parents[1]
    if not (repo_root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "tag", "--list", "--merged", "HEAD", "--sort=-v:refname", "v*"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        tags = [t.lstrip("v") for t in result.stdout.split()]
        latest = next((t for t in tags if t.count(".") == 2), None)
        if latest is None:
            return None

        head_tags = subprocess.check_output(
            ["git", "tag", "--points-at", "HEAD"], cwd=repo_root, text=True
        ).split()
        if f"v{latest}" in head_tags:
            return latest

        parts = [int(x) for x in latest.split(".")]
        parts[-1] += 1
        return ".".join(str(p) for p in parts) + ".dev0"
    except Exception:
        return None


def _load_package_version() -> str:
    """Return a version aligned with current tag strategy."""
    try:
        dist_version = _metadata_version("pdd-cli")
    except PackageNotFoundError:
        dist_version = "0.0.0+unknown"

    git_version = _derive_git_aligned_version()
    if git_version is None:
        return dist_version

    # Prefer git-aligned version when installed metadata is stale for this checkout.
    if dist_version != git_version:
        return git_version
    return dist_version


__version__ = _load_package_version()


def get_version() -> str:
    """Return the installed pdd-cli distribution version."""
    return _load_package_version()


def _setup_cloud_defaults() -> None:
    """Set up default cloud credentials if not already set."""
    # Skip if running in cloud environment to prevent infinite loops
    if os.environ.get("K_SERVICE") or os.environ.get("FUNCTIONS_EMULATOR"):
        return

    # Set Firebase API key if not already set
    if not os.environ.get("NEXT_PUBLIC_FIREBASE_API_KEY"):
        os.environ["NEXT_PUBLIC_FIREBASE_API_KEY"] = _DEFAULT_FIREBASE_API_KEY

    # Set GitHub Client ID if not already set
    if not os.environ.get("GITHUB_CLIENT_ID"):
        os.environ["GITHUB_CLIENT_ID"] = _DEFAULT_GITHUB_CLIENT_ID


# Initialize cloud defaults on package import
_setup_cloud_defaults()
