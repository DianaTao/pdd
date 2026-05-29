from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple, Any, Dict

import click
from rich.console import Console

from ..track_cost import track_cost
from ..sync_main import sync_main
from ..auto_deps_main import auto_deps_main
from ..agentic_sync import _is_github_issue_url, run_agentic_sync, run_global_sync
from ..architecture_sync import sync_prompts_to_architecture
from ..construct_paths import _find_pddrc_file, _load_pddrc_config
from ..core.utils import _run_setup_utility
from ..core.errors import handle_error

console = Console()

DEFAULT_SYNC_BUDGET = 20.0


def _run_agentic_sync_dispatch(
    ctx: click.Context,
    issue_url: str,
    budget: Optional[float] = None,
    skip_verify: bool = False,
    skip_tests: bool = False,
    target_coverage: Optional[float] = None,
    dry_run: bool = False,
    agentic: bool = False,
    no_steer: bool = False,
    max_attempts: Optional[int] = None,
    timeout_adder: float = 0.0,
    no_github_state: bool = False,
    one_session: bool = True,
    durable: bool = False,
    durable_branch: Optional[str] = None,
    no_resume: bool = False,
    durable_max_parallel: Optional[int] = None,
    strength: Optional[float] = None,
    temperature: Optional[float] = None,
    context_override: Optional[str] = None,
) -> Tuple[Any, float, str]:
    """Dispatch to agentic sync runner for GitHub issue URLs."""
    obj = ctx.obj or {}
    try:
        reasoning_time = obj.get("time") if obj.get("time_explicit") else None

        success, message, cost, model = run_agentic_sync(
            issue_url=issue_url,
            verbose=obj.get("verbose", False),
            quiet=obj.get("quiet", False),
            budget=budget,
            skip_verify=skip_verify,
            skip_tests=skip_tests,
            target_coverage=target_coverage,
            dry_run=dry_run,
            agentic_mode=agentic,
            no_steer=no_steer,
            max_attempts=max_attempts or 3,
            timeout_adder=timeout_adder,
            use_github_state=not no_github_state,
            one_session=one_session,
            durable=durable,
            durable_branch=durable_branch,
            no_resume=no_resume,
            durable_max_parallel=durable_max_parallel,
            strength=strength if strength is not None else obj.get("strength"),
            temperature=temperature if temperature is not None else obj.get("temperature"),
            context_override=context_override if context_override is not None else obj.get("context"),
            reasoning_time=reasoning_time,
        )

        if not obj.get("quiet", False):
            click.echo(f"Status: {'Success' if success else 'Failed'}")
            click.echo(f"Message: {message}")
            click.echo(f"Cost: ${cost:.4f}")
            if model and model.lower() not in ("unknown", "n/a", ""):
                click.echo(f"Model: {model}")

        if not success:
            raise click.exceptions.Exit(1)
        
        return message, cost, model
    except (click.Abort, click.exceptions.Exit):
        raise
    except Exception as e:
        handle_error(e, "sync", obj.get("quiet", False))
        return None  # type: ignore


def _run_global_sync_dispatch(
    ctx: click.Context,
    budget: float,
    skip_verify: bool = False,
    skip_tests: bool = False,
    target_coverage: Optional[float] = None,
    dry_run: bool = False,
    agentic: bool = False,
    no_steer: bool = True,
    max_attempts: Optional[int] = None,
    one_session: bool = False,
    timeout_adder: float = 0.0,
    strength: Optional[float] = None,
    temperature: Optional[float] = None,
    context_override: Optional[str] = None,
) -> Tuple[Any, float, str]:
    """Dispatch to global sync runner for no-argument `pdd sync`."""
    obj = ctx.obj or {}
    try:
        success, message, cost, model = run_global_sync(
            verbose=obj.get("verbose", False),
            quiet=obj.get("quiet", False),
            budget=budget,
            skip_verify=skip_verify,
            skip_tests=skip_tests,
            target_coverage=target_coverage,
            dry_run=dry_run,
            agentic_mode=agentic,
            max_attempts=max_attempts or 3,
            timeout_adder=timeout_adder,
            one_session=one_session,
            local=obj.get("local", False),
            strength=strength if strength is not None else obj.get("strength"),
            temperature=temperature if temperature is not None else obj.get("temperature"),
            context_override=context_override if context_override is not None else obj.get("context"),
        )
        if not obj.get("quiet", False):
            click.echo(f"Status: {'Success' if success else 'Failed'}")
            click.echo(f"Message: {message}")
            click.echo(f"Cost: ${cost:.4f}")
            if model and model.lower() not in ("unknown", "n/a", ""):
                click.echo(f"Model: {model}")
        if not success:
            raise click.exceptions.Exit(1)
        return message, cost, model
    except (click.Abort, click.exceptions.Exit):
        raise
    except Exception as e:
        handle_error(e, "global sync", obj.get("quiet", False))
        raise click.exceptions.Exit(1)


def _resolve_global_sync_budget(budget: Optional[float]) -> float:
    """Resolve budget from CLI, .pddrc, or default."""
    if budget is not None:
        return budget
    try:
        pddrc_path = _find_pddrc_file(Path.cwd())
        if pddrc_path:
            config = _load_pddrc_config(pddrc_path)
            default_ctx = config.get("contexts", {}).get("default", {}).get("defaults", {})
            if "budget" in default_ctx:
                return float(default_ctx["budget"])
    except (TypeError, ValueError, KeyError):
        pass
    return DEFAULT_SYNC_BUDGET


def _resolve_global_sync_target_coverage(target_coverage: Optional[float]) -> Optional[float]:
    """Resolve target coverage from CLI or .pddrc."""
    if target_coverage is not None:
        return target_coverage
    try:
        pddrc_path = _find_pddrc_file(Path.cwd())
        if pddrc_path:
            config = _load_pddrc_config(pddrc_path)
            default_ctx = config.get("contexts", {}).get("default", {}).get("defaults", {})
            if "target_coverage" in default_ctx:
                return float(default_ctx["target_coverage"])
    except (TypeError, ValueError, KeyError):
        pass
    return None


@click.command("sync")
@click.argument("basename", required=False)
@click.option("--max-attempts", type=int, default=None, help="Maximum number of fix attempts. Default: 3 or .pddrc value.")
@click.option("--budget", type=float, default=None, help="Maximum total cost for the sync process. Default: 20.0 or .pddrc value.")
@click.option("--skip-verify", is_flag=True, default=False, help="Skip verification step.")
@click.option("--skip-tests", is_flag=True, default=False, help="Skip unit test generation/fixing.")
@click.option("--target-coverage", type=float, default=None, help="Desired coverage percentage. Default: 90.0 or .pddrc value.")
@click.option("--dry-run", is_flag=True, default=False, help="Analyze sync state without executing operations.")
@click.option("--log", is_flag=True, default=False, hidden=True)
@click.option("--no-steer", "no_steer", is_flag=True, default=False, help="Disable interactive steering of sync operations.")
@click.option("--steer-timeout", type=float, default=None, help="Timeout in seconds for steering prompts (default downstream: 8.0).")
@click.option("--agentic", is_flag=True, default=False, help="Use agentic mode for Python.")
@click.option("--timeout-adder", type=float, default=0.0, help="Additional seconds added on top of the per-module wall-clock cap (agentic sync mode).")
@click.option("--no-github-state", is_flag=True, default=False, help="Disable GitHub comment updates (agentic sync mode).")
@click.option("--one-session/--no-one-session", default=None, help="Use one session.")
@click.option("--durable", is_flag=True, default=False, help="Run each module in an isolated worktree and checkpoint to a durable branch.")
@click.option("--durable-branch", type=str, default=None, help="Override the durable checkpoint branch name.")
@click.option("--no-resume", is_flag=True, default=False, help="Ignore existing checkpoint trailers.")
@click.option("--durable-max-parallel", type=int, default=None, help="Cap concurrent module worktrees.")
@click.pass_context
@track_cost
def sync(
    ctx: click.Context,
    basename: Optional[str],
    max_attempts: Optional[int],
    budget: Optional[float],
    skip_verify: bool,
    skip_tests: bool,
    target_coverage: Optional[float],
    dry_run: bool,
    log: bool,
    no_steer: bool,
    steer_timeout: Optional[float],
    agentic: bool,
    timeout_adder: float,
    no_github_state: bool,
    one_session: Optional[bool],
    durable: bool,
    durable_branch: Optional[str],
    no_resume: bool,
    durable_max_parallel: Optional[int]
) -> Tuple[Any, float, str]:
    """Synchronize a prompt with its code, tests, and examples"""
    if log:
        click.echo(click.style("Warning: --log is deprecated, use --dry-run instead.", fg="yellow"), err=True)
        dry_run = True

    resolved_budget = _resolve_global_sync_budget(budget)
    resolved_target_coverage = _resolve_global_sync_target_coverage(target_coverage)

    is_github = basename is not None and _is_github_issue_url(basename)
    
    if not is_github and any([durable, durable_branch is not None, no_resume, durable_max_parallel is not None]):
        raise click.UsageError("Durable sync options require a GitHub issue URL.")
    
    if is_github and not durable and any([durable_branch is not None, no_resume, durable_max_parallel is not None]):
        raise click.UsageError("--durable-branch, --no-resume, and --durable-max-parallel require --durable.")

    if not basename:
        effective_one_session = one_session if one_session is not None else False
        return _run_global_sync_dispatch(
            ctx=ctx,
            budget=resolved_budget,
            skip_verify=skip_verify,
            skip_tests=skip_tests,
            target_coverage=resolved_target_coverage,
            dry_run=dry_run,
            agentic=agentic,
            no_steer=no_steer,
            max_attempts=max_attempts,
            one_session=effective_one_session,
            timeout_adder=timeout_adder,
        )
    elif is_github:
        effective_one_session = one_session if one_session is not None else True
        return _run_agentic_sync_dispatch(
            ctx=ctx,
            issue_url=basename,
            budget=budget,
            skip_verify=skip_verify,
            skip_tests=skip_tests,
            target_coverage=resolved_target_coverage,
            dry_run=dry_run,
            agentic=agentic,
            no_steer=no_steer,
            max_attempts=max_attempts,
            timeout_adder=timeout_adder,
            no_github_state=no_github_state,
            one_session=effective_one_session,
            durable=durable,
            durable_branch=durable_branch,
            no_resume=no_resume,
            durable_max_parallel=durable_max_parallel,
        )
    else:
        try:
            effective_one_session = one_session if one_session is not None else False
            results, cost, model = sync_main(
                ctx=ctx,
                basename=basename,
                max_attempts=max_attempts or 3,
                budget=resolved_budget,
                skip_verify=skip_verify,
                skip_tests=skip_tests,
                target_coverage=resolved_target_coverage,
                dry_run=dry_run,
                agentic_mode=agentic,
                no_steer=no_steer,
                steer_timeout=steer_timeout,
                timeout_adder=timeout_adder,
                one_session=effective_one_session,
            )
            return results, cost, model
        except (click.Abort, click.exceptions.Exit):
            raise
        except Exception as exception:
            handle_error(exception, "sync", ctx.obj.get("quiet", False))
            return None


def _echo_architecture_sync_result(result: dict, *, dry_run: bool) -> None:
    """Render a concise summary for prompt-to-architecture sync."""
    if dry_run:
        click.echo(f"Dry run: would update {result.get('updated_count', 0)} module(s); skipped {result.get('skipped_count', 0)}.")
    else:
        click.echo(f"Updated {result.get('updated_count', 0)} module(s); skipped {result.get('skipped_count', 0)}.")
        
    total_rules = result.get('total_rules')
    total_stories = result.get('total_stories')
    if total_rules is not None and total_stories is not None:
        click.echo(f"Total Contracts: {total_rules} rules, {total_stories} stories found across synced modules.")
        
    for entry in result.get("results", []):
        if entry.get("updated"):
            click.echo(f"UPDATED {entry['filename']}")
            if contract_summary := entry.get("contract_summary"):
                click.echo(f"  Contracts: {len(contract_summary.get('rules', []))} rules, {len(contract_summary.get('stories', []))} stories")
                evidence_status = contract_summary.get('evidence_status')
                if evidence_status == 'stale':
                    click.echo(click.style(f"  Warning: Evidence is STALE for {entry['filename']}", fg="yellow"))
                elif evidence_status == 'missing':
                    click.echo(click.style(f"  Warning: Evidence is MISSING for {entry['filename']}", fg="red"))
        elif not entry.get("success"):
            click.echo(f"ERROR {entry['filename']}: {entry.get('error')}")
            
    if errors := result.get("errors"):
        click.echo("Sync errors:")
        for error in errors:
            click.echo(f"- {error}")
            
    validation = result.get("validation", {})
    if val_errors := validation.get("errors"):
        click.echo("Validation errors:")
        for error in val_errors:
            click.echo(f"- {error['message']}")
    if val_warnings := validation.get("warnings"):
        click.echo("Validation warnings:")
        for warning in val_warnings:
            click.echo(f"- {warning['message']}")


@click.command("sync-architecture")
@click.argument("filenames", nargs=-1)
@click.option("--dry-run", is_flag=True, default=False, help="Analyze sync state without executing.")
@click.pass_context
@track_cost
def sync_architecture(ctx: click.Context, filenames: Tuple[str, ...], dry_run: bool) -> Tuple[Any, float, str]:
    """Sync architecture.json from prompt metadata tags"""
    obj = ctx.obj or {}
    try:
        result = sync_prompts_to_architecture(
            filenames=list(filenames) if filenames else None,
            dry_run=dry_run
        )
        if not obj.get("quiet", False):
            _echo_architecture_sync_result(result, dry_run=dry_run)
        if not result.get("success"):
            raise click.exceptions.Exit(1)
        return result, 0.0, "local"
    except (click.Abort, click.exceptions.Exit):
        raise
    except Exception as e:
        handle_error(e, "sync-architecture", obj.get("quiet", False))
        return None  # type: ignore


@click.command("auto-deps")
@click.argument("prompt_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("directory_path", type=click.Path(exists=False, file_okay=False))
@click.option("--output", type=click.Path(writable=True), default=None, help="Modified prompt output location.")
@click.option("--csv", type=click.Path(writable=True), default=None, help="Dependency CSV location.")
@click.option("--force-scan", is_flag=True, default=False, help="Force rescan.")
@click.option("--include-docs", is_flag=True, default=False, help="Include documentation.")
@click.option("--no-dedup", is_flag=True, default=False, help="Skip redundant inline content removal.")
@click.option("--concurrency", type=int, default=1, help="Max parallel LLM calls.")
@click.pass_context
@track_cost
def auto_deps(
    ctx: click.Context,
    prompt_file: str,
    directory_path: str,
    output: Optional[str],
    csv: Optional[str],
    force_scan: bool,
    include_docs: bool,
    no_dedup: bool,
    concurrency: int,
) -> Tuple[str, float, str]:
    """Analyze project dependencies and update prompt file"""
    try:
        # Pass additional options via ctx.obj for downstream consumption
        ctx.ensure_object(dict)
        ctx.obj["include_docs"] = include_docs
        ctx.obj["no_dedup"] = no_dedup
        ctx.obj["concurrency"] = concurrency

        if directory_path:
            directory_path = directory_path.strip('"').strip("'")

        return auto_deps_main(
            ctx=ctx,
            prompt_file=prompt_file,
            directory_path=directory_path,
            auto_deps_csv_path=csv,
            output=output,
            force_scan=force_scan,
            include_docs=include_docs,
            no_dedup=no_dedup,
            concurrency=concurrency,
        )
    except (click.Abort, click.exceptions.Exit):
        raise
    except Exception as exception:
        handle_error(exception, "auto-deps", ctx.obj.get("quiet", False))
        return None  # type: ignore


@click.command("setup")
@click.pass_context
def setup(ctx: click.Context) -> None:
    """Install shell completion and run setup utility"""
    obj = ctx.obj or {}
    try:
        from .. import cli as cli_module
        cli_module.install_completion(quiet=obj.get("quiet", False))
        _run_setup_utility()
    except (click.Abort, click.exceptions.Exit):
        raise
    except Exception as e:
        handle_error(e, "setup", obj.get("quiet", False))
