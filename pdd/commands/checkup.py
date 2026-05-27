"""
Checkup command — GitHub issue-driven project health check, or local diagnostics.
"""
import click
from pathlib import Path
from typing import Optional, Tuple, Callable, Any

from ..agentic_change import _parse_pr_url
from ..agentic_checkup import run_agentic_checkup
from ..agentic_sync import _is_github_issue_url
from ..track_cost import track_cost
from ..core.errors import handle_error


def checkup_options(f: Callable) -> Callable:
    """Shared options for checkup and legacy-run commands."""
    f = click.option(
        "--validate-arch-includes",
        "validate_arch_includes",
        is_flag=True,
        default=False,
        help="Cross-check architecture.json against module <include> tags (no GitHub issue).",
    )(f)
    f = click.option(
        "--project-root",
        "project_root",
        type=click.Path(exists=True, path_type=Path, file_okay=False),
        default=None,
        help="With --validate-arch-includes: directory to scan (default: current directory).",
    )(f)
    f = click.option(
        "--validate-arch-strict",
        "strict_arch",
        is_flag=True,
        default=False,
        help="With --validate-arch-includes: also validate bundled sample trees (examples/, …).",
    )(f)
    f = click.option(
        "--no-fix",
        is_flag=True,
        default=False,
        help="Report only, don't apply fixes.",
    )(f)
    f = click.option(
        "--timeout-adder",
        type=float,
        default=0.0,
        help="Additional seconds to add to each step's timeout.",
    )(f)
    f = click.option(
        "--no-github-state",
        is_flag=True,
        default=False,
        help="Disable GitHub state persistence.",
    )(f)
    f = click.option(
        "--pr",
        "pr_url",
        type=str,
        default=None,
        help=(
            "PR-mode: verify this existing pull request instead of creating a new one. "
            "Requires --issue. TARGET must NOT be passed."
        ),
    )(f)
    f = click.option(
        "--issue",
        "issue_url_opt",
        type=str,
        default=None,
        help=(
            "PR-mode companion to --pr: the original GitHub issue the PR is meant to "
            "resolve. Used as issue context for verification."
        ),
    )(f)
    f = click.option(
        "--review-loop",
        is_flag=True,
        default=False,
        help="In PR mode, run the primary-reviewer/fixer loop before returning a verdict.",
    )(f)
    f = click.option(
        "--review-only",
        is_flag=True,
        default=False,
        help=(
            "With --review-loop, run only the primary reviewer first pass and do "
            "not invoke the fixer, commit, or push."
        ),
    )(f)
    f = click.option(
        "--reviewers",
        type=str,
        default="codex,claude",
        show_default=True,
        help="Legacy comma-separated role order for --review-loop: reviewer,fixer.",
    )(f)
    f = click.option(
        "--reviewer",
        type=str,
        default=None,
        show_default=False,
        help="Primary reviewer role for --review-loop. Overrides the first --reviewers role.",
    )(f)
    f = click.option(
        "--fixer",
        type=str,
        default=None,
        show_default=False,
        help="Fixer role for --review-loop. Overrides the second --reviewers role.",
    )(f)
    f = click.option(
        "--reviewer-fallback",
        type=str,
        default=None,
        show_default=False,
        help=(
            "Optional secondary reviewer role to invoke once if the primary reviewer "
            "fails (auth/network/exec/sandbox/rate-limit). Must differ from --reviewer "
            "and --fixer."
        ),
    )(f)
    f = click.option(
        "--fixer-fallback",
        type=str,
        default=None,
        show_default=False,
        help=(
            "Optional secondary fixer role to invoke once if the primary fixer "
            "cannot address the reviewer's findings (e.g. a subscription-tier "
            "credential exhaustion such as Claude Code 'You've hit your limit "
            "· resets …'). Must differ from --fixer and --reviewer to preserve "
            "reviewer/fixer role independence."
        ),
    )(f)
    f = click.option(
        "--max-review-rounds",
        type=int,
        default=5,
        show_default=True,
        help="Maximum primary-reviewer/fixer rounds.",
    )(f)
    f = click.option(
        "--max-review-cost",
        type=float,
        default=50.0,
        show_default=True,
        help="Maximum review-loop LLM cost in USD.",
    )(f)
    f = click.option(
        "--max-review-minutes",
        type=float,
        default=90.0,
        show_default=True,
        help="Maximum wall-clock minutes for the review loop.",
    )(f)
    f = click.option(
        "--require-all-reviewers-clean/--no-require-all-reviewers-clean",
        default=True,
        show_default=True,
        help="Compatibility flag; the primary reviewer is the authoritative ship gate.",
    )(f)
    f = click.option(
        "--continue-on-reviewer-limit",
        is_flag=True,
        default=False,
        help=(
            "Report provider/rate/context-limit/auth/network/sandbox reviewer "
            "failures as degraded instead of failed. This never marks an active "
            "reviewer clean or continues mutation without a completed review."
        ),
    )(f)
    f = click.option(
        "--require-final-fresh-review/--no-require-final-fresh-review",
        default=True,
        show_default=True,
        help="Compatibility flag; the primary reviewer's clean verification is final.",
    )(f)
    f = click.option(
        "--blocking-severities",
        type=str,
        default=None,
        show_default=False,
        help=(
            "Comma-separated highest-priority severities for review-loop reporting "
            "and prompt guidance. The fixer still receives every valid reviewer "
            "finding. Default: blocker,critical,medium. Unknown severities are dropped."
        ),
    )(f)
    f = click.option(
        "--clean-reviewer-states",
        type=str,
        default=None,
        show_default=False,
        help=(
            "Compatibility parser for downstream reviewer-status gates. Default: "
            "clean. The tokens 'failed', 'degraded', and 'missing' are always "
            "treated as not-clean regardless of this flag."
        ),
    )(f)
    f = click.option(
        "--fallback-reviewer-on-failure",
        is_flag=True,
        default=False,
        help=(
            "Opt-in. When the primary reviewer ends in 'failed' or 'missing' "
            "on the initial review pass of a round, run a second review pass "
            "using the configured fixer's identity as a fallback reviewer."
        ),
    )(f)
    return f


class CheckupGroup(click.Group):
    """Custom Click Group to support legacy positional TARGET argument.
    
    If the first argument does not match a known subcommand (like 'contract'),
    it is treated as a positional argument (TARGET) via the hidden 'legacy-run' 
    subcommand.
    """
    def resolve_command(self, ctx, args):
        try:
            # Try to resolve normally first (matches 'contract')
            return super().resolve_command(ctx, args)
        except click.UsageError:
            # If no command found, or if an option was found that doesn't belong to a command,
            # delegate to the hidden 'legacy-run' command which handles positional TARGET.
            # We must pass the original args so legacy-run can parse them.
            return 'legacy-run', self.get_command(ctx, 'legacy-run'), args


def _run_checkup_logic(
    ctx: click.Context,
    target: Optional[str],
    validate_arch_includes: bool,
    project_root: Optional[Path],
    strict_arch: bool,
    no_fix: bool,
    timeout_adder: float,
    no_github_state: bool,
    pr_url: Optional[str],
    issue_url_opt: Optional[str],
    review_loop: bool,
    review_only: bool,
    reviewers: str,
    reviewer: Optional[str],
    fixer: Optional[str],
    reviewer_fallback: Optional[str],
    fixer_fallback: Optional[str],
    max_review_rounds: int,
    max_review_cost: float,
    max_review_minutes: float,
    require_all_reviewers_clean: bool,
    continue_on_reviewer_limit: bool,
    require_final_fresh_review: bool,
    blocking_severities: Optional[str],
    clean_reviewer_states: Optional[str],
    fallback_reviewer_on_failure: bool,
) -> Optional[Tuple[str, float, str]]:
    """Core logic for the checkup command, shared between group function and legacy-run."""
    
    ctx.ensure_object(dict)

    if validate_arch_includes:
        if target is not None or pr_url is not None or issue_url_opt is not None:
            raise click.BadParameter(
                "Do not pass TARGET, --pr, or --issue when using --validate-arch-includes.",
                param_hint="'TARGET'",
            )
        root = project_root if project_root is not None else Path.cwd()
        from ..architecture_include_validation import run_validate_arch_includes_cli

        run_validate_arch_includes_cli(root, strict=strict_arch, quiet=ctx.obj.get("quiet", False))
        return "validate-arch-includes: ok", 0.0, ""

    # PR-mode argument validation
    pr_mode = pr_url is not None or issue_url_opt is not None
    if review_loop and not pr_mode:
        raise click.BadParameter(
            "--review-loop requires --pr and --issue.",
            param_hint="'--review-loop'",
        )
    if review_only and not review_loop:
        raise click.BadParameter(
            "--review-only requires --review-loop.",
            param_hint="'--review-only'",
        )
    if review_loop and no_fix and not review_only:
        raise click.BadParameter(
            "--review-loop cannot be combined with --no-fix; the loop owns the fixer step.",
            param_hint="'--review-loop'",
        )
    if review_loop and max_review_rounds < 1:
        raise click.BadParameter(
            "--max-review-rounds must be >= 1.",
            param_hint="'--max-review-rounds'",
        )
    if review_loop and max_review_cost <= 0:
        raise click.BadParameter(
            "--max-review-cost must be > 0.",
            param_hint="'--max-review-cost'",
        )
    if review_loop and max_review_minutes <= 0:
        raise click.BadParameter(
            "--max-review-minutes must be > 0.",
            param_hint="'--max-review-minutes'",
        )
    if pr_mode:
        if target is not None:
            raise click.BadParameter(
                "Do not pass TARGET when using --pr/--issue; they are mutually exclusive.",
                param_hint="'TARGET'",
            )
        if pr_url is None or issue_url_opt is None:
            raise click.BadParameter(
                "--pr and --issue must both be provided in PR mode.",
                param_hint="'--pr/--issue'",
            )
        if _parse_pr_url(pr_url) is None:
            raise click.BadParameter(
                "--pr must be a GitHub pull-request URL "
                "(e.g., https://github.com/org/repo/pull/123).",
                param_hint="'--pr'",
            )
        if not _is_github_issue_url(issue_url_opt):
            raise click.BadParameter(
                "--issue must be a GitHub issue URL "
                "(e.g., https://github.com/org/repo/issues/123).",
                param_hint="'--issue'",
            )
        if not no_fix and not review_loop:
            click.echo(
                "Warning: --pr forces --no-fix because push-back to the PR "
                "is not yet implemented. Generated fixes inside the PR "
                "worktree would not reach the PR. Re-invoke without --pr "
                "(or with an issue TARGET) to apply fixes.",
                err=True,
            )
            no_fix = True
        effective_issue_url = issue_url_opt
    else:
        if not target:
            raise click.UsageError(
                "Missing argument 'TARGET'. For local checks use "
                "`pdd checkup --validate-arch-includes`. For PR verification use "
                "`pdd checkup --pr <pr-url> --issue <issue-url>`."
            )

        if not _is_github_issue_url(target):
            raise click.BadParameter(
                "TARGET must be a GitHub issue URL "
                "(e.g., https://github.com/org/repo/issues/123), "
                "or use --pr/--issue for PR verification, "
                "or --validate-arch-includes for architecture / include validation.",
                param_hint="'TARGET'",
            )
        effective_issue_url = target

    quiet = ctx.obj.get("quiet", False)
    verbose = ctx.obj.get("verbose", False)

    try:
        success, message, cost, model = run_agentic_checkup(
            issue_url=effective_issue_url,
            verbose=verbose,
            quiet=quiet,
            no_fix=no_fix,
            timeout_adder=timeout_adder,
            use_github_state=not no_github_state,
            reasoning_time=ctx.obj.get("time") if ctx.obj.get("time_explicit") else None,
            pr_url=pr_url,
            review_loop=review_loop,
            review_only=review_only,
            reviewers=reviewers,
            reviewer=reviewer,
            fixer=fixer,
            reviewer_fallback=reviewer_fallback,
            fixer_fallback=fixer_fallback,
            max_review_rounds=max_review_rounds,
            max_review_cost=max_review_cost,
            max_review_minutes=max_review_minutes,
            require_all_reviewers_clean=require_all_reviewers_clean,
            continue_on_reviewer_limit=continue_on_reviewer_limit,
            require_final_fresh_review=require_final_fresh_review,
            blocking_severities=blocking_severities,
            clean_reviewer_states=clean_reviewer_states,
            fallback_reviewer_on_failure=fallback_reviewer_on_failure,
        )

        if not quiet:
            status = "Success" if success else "Failed"
            click.echo(f"Status: {status}")
            click.echo(f"Message: {message}")
            click.echo(f"Cost: ${cost:.4f}")
            click.echo(f"Model: {model}")

        if not success:
            raise click.exceptions.Exit(1)

        return message, cost, model

    except (click.Abort, click.exceptions.Exit):
        raise
    except Exception as exception:
        handle_error(exception, "checkup", ctx.obj.get("quiet", False))
        return None


@click.group(
    "checkup", 
    cls=CheckupGroup,
    invoke_without_command=True, 
    context_settings=dict(allow_interspersed_args=False, ignore_unknown_options=True, allow_extra_args=True)
)
@checkup_options
@click.pass_context
@track_cost
def checkup(ctx: click.Context, **kwargs) -> Optional[Tuple[str, float, str]]:
    """
    Run agentic health checkup from a GitHub issue, or local diagnostics.

    \b
    GitHub mode (default): TARGET is an issue URL.
    PR mode: pass --pr <pr-url> and --issue <issue-url> to verify an existing PR
             against its source issue without creating a new PR.
    Local mode: pass --validate-arch-includes (no TARGET) to cross-validate
    architecture.json entries against module prompt <include> tags.
    """
    if ctx.invoked_subcommand is not None and ctx.invoked_subcommand != 'legacy-run':
        return None

    # Handle legacy call directly if no subcommand provided
    if ctx.invoked_subcommand is None:
        target = ctx.args[0] if ctx.args else None
        # Click only populates kwargs for parsed options. positional args in ctx.args
        # are NOT in kwargs.
        return _run_checkup_logic(ctx, target, **kwargs)
    
    return None


@checkup.command("legacy-run", hidden=True, context_settings=dict(ignore_unknown_options=False, allow_extra_args=False))
@click.argument('target', required=False)
@checkup_options
@click.pass_context
def legacy_run(ctx, target, **kwargs):
    """Hidden command to handle legacy positional arguments."""
    # We prefer the options passed directly to legacy-run if it was invoked via resolve_command
    return _run_checkup_logic(ctx, target, **kwargs)


@checkup.group("contract")
def contract_group():
    """Module interface contract commands."""
    pass


@contract_group.command("check")
@click.argument("prompt", required=True)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Verify that all <include> tags resolve to files that actually exist.",
)
@click.pass_context
def contract_check(ctx, prompt, strict):
    """
    Validate module interface contract for a specific PROMPT.

    Delegates to --validate-arch-includes logic for the specific module.
    """
    from ..architecture_include_validation import run_validate_arch_includes_cli
    root = Path.cwd()
    run_validate_arch_includes_cli(root, strict=strict, quiet=ctx.obj.get("quiet", False))
