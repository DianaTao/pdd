# pylint: disable=duplicate-code
"""
Contract authoring quality utilities (pdd contracts …).
"""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..contract_check import (
    ContractIssue,
    ContractResult,
    check_directory,
    check_prompt,
    check_stories,
    run_llm_ambiguity_pass,
)
from ..contract_compile import ContractIR, compile_directory, compile_prompt
from ..contract_drift import DriftFinding, DriftResult, structural_drift, semantic_drift
from ..contract_gate_service import GateRun, StageResult, run_gate
from ..contract_ir import parse_prompt_contracts
from ..contract_review import ReviewFinding, ReviewResult, run_llm_review_pass
from ..contract_review_pipeline import run_interactive_review
from ..contracts_author import AuthorResult, author_contracts, MODE_GREENFIELD, MODE_RETROFIT

_console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------

def _render_issue(issue: ContractIssue) -> None:
    """Print one ContractIssue to the console."""
    badge_style = "bold red" if issue.level == "error" else "bold yellow"
    badge = f"[{badge_style}]{issue.level.upper()}[/{badge_style}]"

    code_str = f"[dim cyan]{escape(issue.code)}[/dim cyan]"
    rid_str = (
        f"  [dim magenta]{escape(issue.rule_id)}[/dim magenta]"
        if issue.rule_id
        else ""
    )
    loc_str = f"  [dim][{escape(issue.section)}][/dim]" if issue.section else ""

    _console.print(f"  {badge}  {code_str}{rid_str}{loc_str}  {escape(issue.message)}")

    if issue.line:
        _console.print(f"       [dim italic]{escape(issue.line[:120])}[/dim italic]")

    if issue.interpretations:
        _console.print("       Possible interpretations:")
        for idx, interp in enumerate(issue.interpretations, 1):
            _console.print(f"         {idx}. {escape(interp)}")

    if issue.suggestion and "<add a precise" not in issue.suggestion:
        _console.print(
            f"       [cyan]Suggestion:[/cyan]\n"
            f"         [green]{escape(issue.suggestion)}[/green]"
        )


def _render_result(result: ContractResult, *, quiet: bool = False) -> None:
    """Print a ContractResult header and all its issues."""
    if not result.issues:
        if not quiet:
            _console.print(f"[bold]{result.path}[/bold]  [green]✓ clean[/green]")
        return
    _console.print(
        f"[bold]{result.path}[/bold]  "
        f"[yellow]{result.warn_count} warn[/yellow]  "
        f"[red]{result.error_count} error[/red]"
    )
    for issue in result.issues:
        _render_issue(issue)


def _render_ir(result: ContractIR, *, quiet: bool = False) -> None:
    """Print a compiled ContractIR summary."""
    if not result.has_contract_rules:
        if not quiet:
            _console.print(
                f"[bold]{result.path}[/bold]  "
                "[dim]No <contract_rules> section — no contract IR.[/dim]"
            )
        return

    status = "[green]compiled[/green]" if result.error_count == 0 else "[red]failed[/red]"
    _console.print(
        f"[bold]{result.path}[/bold]  {status}  "
        f"[cyan]{result.rule_count} rules[/cyan]  "
        f"[red]{result.error_count} errors[/red]"
    )
    for rule in result.rules:
        obligations = ", ".join(
            f"{obligation.type}:{obligation.modal}"
            for obligation in rule.obligations
        ) or "-"
        _console.print(
            f"  [magenta]{escape(rule.id)}[/magenta]  "
            f"{escape(rule.title or '-') }  "
            f"[dim]condition:[/dim] {escape(rule.condition or '-') }  "
            f"[dim]obligations:[/dim] {escape(obligations)}"
        )
    for error in result.compile_errors:
        _console.print(
            f"  [bold red]ERROR[/bold red]  "
            f"[dim cyan]{escape(error.code)}[/dim cyan]  "
            f"[dim magenta]{escape(error.rule_id)}[/dim magenta]  "
            f"{escape(error.message)}"
        )
        if error.line:
            _console.print(f"       [dim italic]{escape(error.line[:120])}[/dim italic]")


# ---------------------------------------------------------------------------
# Click group and command
# ---------------------------------------------------------------------------

@click.group(name="contracts")
def contracts_group() -> None:
    """Contract authoring quality utilities."""


contracts_cli = contracts_group


@contracts_group.command("check")
@click.argument("target", type=click.Path(exists=True))
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Treat all warnings as errors (exit 2 even for warnings).",
)
@click.option(
    "--stories",
    "stories_dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Scan a user-story directory for ## Covers rule-ID validity.",
)
@click.option(
    "--llm-ambiguity",
    "llm_ambiguity",
    is_flag=True,
    default=False,
    help="Run optional LLM ambiguity review on <contract_rules> terms.",
)
@click.pass_context
def contracts_check(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches
    ctx: click.Context,
    target: str,
    as_json: bool,
    strict: bool,
    stories_dir: Optional[str],
    llm_ambiguity: bool,
) -> None:
    """Check prompt contract sections for structural authoring defects.

    \b
    Examples:
      pdd contracts check prompts/foo_python.prompt
      pdd contracts check prompts/
      pdd contracts check --json prompts/
      pdd contracts check --strict prompts/foo_python.prompt
      pdd contracts check --stories user_stories/ prompts/foo_python.prompt
      pdd contracts check --llm-ambiguity prompts/foo_python.prompt

    \b
    Checks (deterministic, no LLM required):
      DUPLICATE_ID        — same rule ID used more than once
      MALFORMED_ID        — ID prefix doesn't match R-NNN or sequential N.
      NON_SEQUENTIAL_ID   — gap in explicit rule IDs (warn only)
      MISSING_MODAL       — rule lacks MUST / MUST NOT / MAY / SHOULD
      VAGUE_TERM          — vague phrase without <vocabulary> definition
      UNKNOWN_COVERAGE_REF — <coverage> cites an ID not in <contract_rules>
      UNCOVERED_MUST_NOT  — MUST NOT rule absent from <coverage> (when present)
      UNKNOWN_STORY_REF   — story ## Covers cites an unknown rule ID

    \b
    Exit codes:
      0  no issues
      1  warnings only (unless --strict)
      2  errors present, or any issue with --strict
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)
    verbose: bool = obj.get("verbose", False)
    strength: float = obj.get("strength", 0.5)
    temperature: float = obj.get("temperature", 0.0)
    time_val: Optional[float] = obj.get("time")

    all_results: list[ContractResult] = []
    target_path = Path(target)

    # Scan a single prompt file
    if target_path.is_file():
        result = check_prompt(target_path, strict=strict)
        if llm_ambiguity:
            llm_issues = run_llm_ambiguity_pass(
                target_path,
                strength=strength,
                temperature=temperature,
                time=time_val,
                verbose=verbose,
            )
            if strict:
                for issue in llm_issues:
                    issue.level = "error"
            result.issues.extend(llm_issues)
        all_results.append(result)

    # Scan a directory of prompts
    elif target_path.is_dir():
        for prompt_result in check_directory(target_path, strict=strict):
            if llm_ambiguity:
                llm_issues = run_llm_ambiguity_pass(
                    prompt_result.path,
                    strength=strength,
                    temperature=temperature,
                    time=time_val,
                    verbose=verbose,
                )
                if strict:
                    for issue in llm_issues:
                        issue.level = "error"
                prompt_result.issues.extend(llm_issues)
            all_results.append(prompt_result)

    # Scan user-story directory
    if stories_dir is not None:
        prompts_dir = target_path if target_path.is_dir() else target_path.parent
        all_results.extend(
            check_stories(Path(stories_dir), prompts_dir, strict=strict)
        )

    # Output
    if as_json:
        click.echo(_json.dumps([r.as_dict() for r in all_results], indent=2))
    else:
        for result in all_results:
            _render_result(result, quiet=quiet)

    # Exit code
    total_errors = sum(r.error_count for r in all_results)
    total_warns = sum(r.warn_count for r in all_results)

    if total_errors > 0 or (strict and total_warns > 0):
        raise click.exceptions.Exit(2)
    if total_warns > 0:
        raise click.exceptions.Exit(1)


@contracts_group.command("compile")
@click.argument("target", type=click.Path(exists=True))
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output compiled contract IR as JSON.",
)
@click.option(
    "--authoring",
    "authoring_json",
    is_flag=True,
    default=False,
    help="Emit full prompt_contract_ir.v1 authoring IR instead of obligations IR.",
)
@click.pass_context
def contracts_compile(
    ctx: click.Context,
    target: str,
    as_json: bool,
    authoring_json: bool,
) -> None:
    """Compile <contract_rules> into deterministic JSON contract IR.

    \b
    Examples:
      pdd contracts compile prompts/foo_python.prompt
      pdd contracts compile --json prompts/foo_python.prompt
      pdd contracts compile prompts/

    \b
    The v1 compiler is intentionally conservative. It requires each rule to
    have an explicit stable ID such as R1, a parseable "When ..." condition,
    and at least one observable obligation such as:
      MUST return HTTP 409
      MUST write one upload record
      MUST NOT write a new upload record
      MUST NOT call provider_client
      MUST emit refund_rejected
      MUST raise ValueError

    Prompts without <contract_rules> are legacy-safe and exit 0.
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)
    target_path = Path(target)

    if authoring_json:
        if target_path.is_file():
            ir_list = [parse_prompt_contracts(target_path)]
        else:
            ir_list = [
                parse_prompt_contracts(p)
                for p in sorted(target_path.rglob("*.prompt"))
            ]
        if as_json:
            click.echo(_json.dumps([ir.as_dict() for ir in ir_list], indent=2))
        else:
            for ir in ir_list:
                if not quiet:
                    _console.print(
                        f"[bold]{ir.path}[/bold]  "
                        f"[cyan]{ir.version}[/cyan]  "
                        f"rules={len(ir.rules)}"
                    )
        raise click.exceptions.Exit(0)

    if target_path.is_file():
        results = [compile_prompt(target_path)]
    else:
        results = compile_directory(target_path)

    if as_json:
        payload = [r.as_dict() for r in results]
        if not authoring_json:
            for item in payload:
                item.setdefault("ir_kind", "pdd.contract_ir.v1")
        click.echo(_json.dumps(payload, indent=2))
    else:
        for result in results:
            _render_ir(result, quiet=quiet)

    if any(result.error_count > 0 for result in results):
        raise click.exceptions.Exit(2)


def _render_review_finding(finding: ReviewFinding) -> None:
    """Print one advisory review finding."""
    _console.print(
        f"  [cyan]{escape(finding.finding_id)}[/cyan]  "
        f"[dim]{escape(finding.type)}[/dim]  "
        f"rule={escape(finding.rule_id or '-')}"
    )
    if finding.term:
        _console.print(f"       term: {escape(finding.term)}")
    if finding.interpretations:
        for idx, interp in enumerate(finding.interpretations, 1):
            _console.print(f"         {idx}. {escape(interp)}")
    if finding.suggested_definition:
        _console.print(f"       [green]Suggestion:[/green] {escape(finding.suggested_definition)}")


def _render_review_result(result: ReviewResult, *, quiet: bool = False) -> None:
    """Print review results (advisory — does not affect exit code by itself)."""
    if result.error and not result.findings:
        _console.print(f"[bold]{result.path}[/bold]  [red]{escape(result.error)}[/red]")
        return
    if not result.findings:
        if not quiet:
            _console.print(f"[bold]{result.path}[/bold]  [green]no findings[/green]")
        return
    _console.print(
        f"[bold]{result.path}[/bold]  "
        f"[yellow]{len(result.findings)} finding(s)[/yellow]  "
        f"[dim](advisory)[/dim]"
    )
    for finding in result.findings:
        _render_review_finding(finding)


@contracts_group.command("review")
@click.argument("target", type=click.Path(exists=True))
@click.option("--llm", "use_llm", is_flag=True, required=True, help="Run LLM review (required).")
@click.option("--coverage", "include_coverage", is_flag=True, default=False, help="Include coverage matrix in context.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output findings as JSON.")
@click.option(
    "--interactive",
    is_flag=True,
    default=False,
    help="Record human decisions in <contract_review>.",
)
@click.option(
    "--stories-dir",
    "stories_dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Stories directory for coverage context.",
)
@click.option(
    "--tests-dir",
    "tests_dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Tests directory for coverage context.",
)
@click.pass_context
def contracts_review(  # pylint: disable=too-many-arguments,too-many-locals
    ctx: click.Context,
    target: str,
    use_llm: bool,  # pylint: disable=unused-argument
    include_coverage: bool,
    as_json: bool,
    interactive: bool,
    stories_dir: Optional[str],
    tests_dir: Optional[str],
) -> None:
    """Advisory LLM review of contract IR (not a CI gate).

    \b
    Examples:
      pdd contracts review --llm prompts/foo_python.prompt
      pdd contracts review --llm --coverage prompts/foo_python.prompt
      pdd contracts review --llm --json prompts/foo_python.prompt
      pdd contracts review --llm --interactive prompts/foo_python.prompt

    Human rejection is recorded in <contract_review> and does not fail CI.
    Prefer ``pdd contracts check`` for deterministic gates.
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)
    verbose: bool = obj.get("verbose", False)
    strength: float = obj.get("strength", 0.5)
    temperature: float = obj.get("temperature", 0.0)
    time_val: Optional[float] = obj.get("time")

    target_path = Path(target)
    paths = [target_path] if target_path.is_file() else sorted(target_path.rglob("*.prompt"))
    stories_path = Path(stories_dir) if stories_dir else None
    tests_path = Path(tests_dir) if tests_dir else None

    all_reviews: list[ReviewResult] = []
    for prompt_path in paths:
        if prompt_path.name.lower().endswith("_llm.prompt"):
            continue
        review = run_llm_review_pass(
            prompt_path,
            strength=strength,
            temperature=temperature,
            time=time_val,
            verbose=verbose,
            include_coverage=include_coverage,
            stories_dir=stories_path,
            tests_dir=tests_path,
        )
        all_reviews.append(review)

        if interactive and review.findings:
            try:
                from rich.prompt import Prompt  # pylint: disable=import-outside-toplevel
                run_interactive_review(
                    prompt_path,
                    review,
                    (Prompt.ask, Prompt.ask),
                )
            except ImportError:
                _console.print("[yellow]rich.prompt required for --interactive[/yellow]")

    if as_json:
        click.echo(_json.dumps([r.as_dict() for r in all_reviews], indent=2))
    else:
        for review in all_reviews:
            _render_review_result(review, quiet=quiet)

    # Advisory command always exits 0 unless parse/file errors
    if any(r.error and not r.findings for r in all_reviews):
        raise click.exceptions.Exit(2)


# ---------------------------------------------------------------------------
# pdd contracts gate
# ---------------------------------------------------------------------------

def _render_gate_run(run: GateRun) -> None:
    """Print a stage-by-stage gate table to the console."""
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("status", width=6)
    table.add_column("stage", width=20)
    table.add_column("detail")

    status_map = {0: "[green]pass[/green]", 1: "[yellow]warn[/yellow]", 2: "[red]fail[/red]"}

    for stage in run.stages:
        if stage.skipped:
            status = "[dim]skip[/dim]"
        else:
            status = status_map.get(stage.exit_code, "[red]fail[/red]")
        table.add_row(status, escape(stage.name), escape(stage.detail))

    _console.print(table)
    _console.print(
        f"  exit [bold]{run.exit_code}[/bold]  "
        f"([green]0=pass[/green] / [yellow]1=warn[/yellow] / [red]2=fail[/red])"
    )


@contracts_group.command("gate")
@click.argument("target", type=click.Path(exists=True))
@click.option("--stories-dir", "stories_dir", type=click.Path(exists=True, file_okay=False), default=None,
              help="User-stories directory.")
@click.option("--tests-dir", "tests_dir", type=click.Path(exists=True, file_okay=False), default=None,
              help="Tests directory for coverage.")
@click.option("--strict", is_flag=True, default=False,
              help="Treat unchecked coverage rules as errors (exit 2).")
@click.option("--skip-stories-lint", is_flag=True, default=False,
              help="Skip user-story lint in stage 1 (faster).")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output gate result as JSON.")
@click.pass_context
def contracts_gate(
    ctx: click.Context,
    target: str,
    stories_dir: Optional[str],
    tests_dir: Optional[str],
    strict: bool,
    skip_stories_lint: bool,
    as_json: bool,
) -> None:
    """CI gate: run the full deterministic pipeline in one command. No LLM.

    \b
    Stages (in order, fail-fast):
      1. prompt-lint     — deterministic lint only
      2. contracts-check — structural authoring checks
      3. contracts-compile — compile rules into IR
      4. coverage        — rule-to-evidence matrix

    \b
    Exit codes:
      0  all stages pass
      1  warnings (no errors)
      2  one or more errors

    \b
    Examples:
      pdd contracts gate prompts/foo_python.prompt
      pdd contracts gate --strict --stories-dir user_stories/ prompts/
      pdd contracts gate --json prompts/foo_python.prompt
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)

    run = run_gate(
        Path(target),
        stories_dir=Path(stories_dir) if stories_dir else None,
        tests_dir=Path(tests_dir) if tests_dir else None,
        strict=strict,
        skip_stories_lint=skip_stories_lint,
    )

    if as_json:
        click.echo(_json.dumps(run.as_dict(), indent=2))
    else:
        if not quiet:
            _render_gate_run(run)

    raise click.exceptions.Exit(run.exit_code)


# ---------------------------------------------------------------------------
# pdd contracts drift
# ---------------------------------------------------------------------------

def _render_drift_result(result: DriftResult, *, quiet: bool = False) -> None:
    """Print a DriftResult to the console."""
    if result.error:
        _console.print(f"[red]error:[/red] {escape(result.error)}")
    if not result.has_drift:
        if not quiet:
            _console.print(f"[green]✓ no drift detected[/green]  "
                           f"({escape(result.prompt_path)} ↔ {escape(result.code_path)})")
        return
    _console.print(
        f"[bold]{escape(result.prompt_path)}[/bold] ↔ [bold]{escape(result.code_path)}[/bold]  "
        f"[yellow]{result.finding_count} finding(s)[/yellow]"
    )
    for f in result.structural_findings:
        _console.print(
            f"  [red]structural[/red]  [magenta]{escape(f.rule_id)}[/magenta]  "
            f"[dim]{escape(f.term)}[/dim]  {escape(f.message)}"
        )
        if f.line:
            _console.print(f"    line {f.line_number}: [dim italic]{escape(f.line[:120])}[/dim italic]")
    for f in result.semantic_findings:
        _console.print(
            f"  [yellow]semantic[/yellow]  [magenta]{escape(f.rule_id)}[/magenta]  "
            f"[dim]{escape(f.confidence)}[/dim]  {escape(f.message)}"
        )


@contracts_group.command("drift")
@click.argument("prompt_file", type=click.Path(exists=True))
@click.argument("code_file", type=click.Path(exists=True), required=False, default=None)
@click.option("--semantic", "use_semantic", is_flag=True, default=False,
              help="Run LLM semantic drift check in addition to structural (advisory).")
@click.option("--strict", is_flag=True, default=False,
              help="Exit non-zero on any structural finding.")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output findings as JSON.")
@click.pass_context
def contracts_drift(
    ctx: click.Context,
    prompt_file: str,
    code_file: Optional[str],
    use_semantic: bool,
    strict: bool,
    as_json: bool,
) -> None:
    """Detect drift between a prompt's contract rules and its paired code file.

    \b
    Two check types:
      structural (default, deterministic): scans code for MUST NOT terms.
      semantic   (--semantic, LLM):        checks whether MUST obligations
                                           appear to be implemented.

    Structural drift: exits non-zero with --strict.
    Semantic drift:   always advisory (exits 0) unless --strict.

    \b
    Examples:
      pdd contracts drift prompts/foo_python.prompt src/foo.py
      pdd contracts drift --semantic prompts/foo_python.prompt src/foo.py
      pdd contracts drift --strict --json prompts/foo_python.prompt src/foo.py
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)
    verbose: bool = obj.get("verbose", False)
    strength: float = obj.get("strength", 0.5)
    temperature: float = obj.get("temperature", 0.0)
    time_val: Optional[float] = obj.get("time")

    prompt_path = Path(prompt_file)
    code_path = Path(code_file) if code_file else None

    # Try to auto-detect code file from prompt name
    if code_path is None:
        # foo_python.prompt → pdd/foo.py or src/foo.py
        stem = prompt_path.stem.replace("_python", "").replace("_typescript", "")
        candidates = [
            prompt_path.parent.parent / "pdd" / f"{stem}.py",
            prompt_path.parent.parent / "src" / f"{stem}.py",
            prompt_path.parent.parent / f"{stem}.py",
        ]
        for c in candidates:
            if c.is_file():
                code_path = c
                if not quiet:
                    _console.print(f"[dim]auto-detected code file: {c}[/dim]")
                break
        if code_path is None:
            raise click.UsageError(
                "CODE_FILE argument is required (auto-detection failed). "
                "Usage: pdd contracts drift PROMPT_FILE CODE_FILE"
            )

    if use_semantic:
        result = semantic_drift(
            prompt_path,
            code_path,
            strength=strength,
            temperature=temperature,
            time=time_val,
            verbose=verbose,
        )
    else:
        findings = structural_drift(prompt_path, code_path)
        from ..contract_drift import DriftResult  # pylint: disable=import-outside-toplevel
        result = DriftResult(
            prompt_path=str(prompt_path),
            code_path=str(code_path),
            structural_findings=findings,
        )

    if as_json:
        click.echo(_json.dumps(result.as_dict(), indent=2))
    else:
        _render_drift_result(result, quiet=quiet)

    if strict and result.has_drift:
        raise click.exceptions.Exit(1)


# ---------------------------------------------------------------------------
# pdd contracts author
# ---------------------------------------------------------------------------

def _render_author_result(result: AuthorResult, *, quiet: bool = False) -> None:
    """Print author suggestions to the console."""
    if result.skipped:
        _console.print(
            "[yellow]<contract_rules> already present — use --force to overwrite.[/yellow]"
        )
        return
    if result.error:
        _console.print(f"[red]error:[/red] {escape(result.error)}")
        return

    _console.print(f"[bold]mode:[/bold] {escape(result.mode)}")

    if result.suggested_rules:
        _console.print("\n[bold cyan]Suggested <contract_rules>[/bold cyan]")
        for rule in result.suggested_rules:
            _console.print(f"  {escape(rule)}")

    if result.suggested_vocabulary:
        _console.print("\n[bold cyan]Suggested <vocabulary>[/bold cyan]")
        for term in result.suggested_vocabulary:
            _console.print(f"  {escape(term)}")

    if result.suggested_acceptance_tests:
        _console.print("\n[bold cyan]Suggested <acceptance_tests>[/bold cyan]")
        for test in result.suggested_acceptance_tests:
            _console.print(f"  {escape(test)}")

    if not result.dry_run:
        formal_part = (
            f", {result.formalization_written} formalization(s)"
            if result.formalization_written > 0
            else ""
        )
        _console.print(
            f"\n[green]wrote:[/green] "
            f"{result.rules_written} rule(s), "
            f"{result.acceptance_tests_written} acceptance test(s)"
            f"{formal_part}"
        )
        # Quality summary (only when writeback actually happened)
        if result.rules_written > 0:
            errors_style = "red" if result.compile_errors > 0 else "green"
            warns_style = "yellow" if result.new_lint_warnings > 0 else "green"
            _console.print(
                f"[bold]quality:[/bold] "
                f"compile_errors=[{errors_style}]{result.compile_errors}[/{errors_style}]  "
                f"lint_warnings=[{warns_style}]{result.new_lint_warnings}[/{warns_style}]"
            )
            if not result.quality_ok:
                _console.print(
                    "[yellow]  Run `pdd contracts compile` and `pdd contracts check` "
                    "for details.[/yellow]"
                )


@contracts_group.command("author")
@click.argument("prompt_file", type=click.Path(exists=True))
@click.argument("code_file", type=click.Path(), required=False, default=None)
@click.option("--mode", type=click.Choice(["greenfield", "retrofit"]), default=None,
              help="Authoring mode (auto-detected if omitted).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print suggestions without writing to the prompt file.")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing <contract_rules> if present.")
@click.option("--formalize", is_flag=True, default=False,
              help="After writing rules, invoke formalize LLM to append a <formalization> block.")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output result as JSON.")
@click.pass_context
def contracts_author(
    ctx: click.Context,
    prompt_file: str,
    code_file: Optional[str],
    mode: Optional[str],
    dry_run: bool,
    force: bool,
    formalize: bool,
    as_json: bool,
) -> None:
    """LLM-assisted authoring of <contract_rules> for a prompt. Requires --llm via env.

    \b
    Modes:
      greenfield  (default when no code file): design rules from requirements.
      retrofit    (default when code file present): infer rules from existing code.

    \b
    Examples:
      pdd contracts author prompts/foo_python.prompt
      pdd contracts author --mode greenfield prompts/foo_python.prompt
      pdd contracts author prompts/foo_python.prompt pdd/foo.py
      pdd contracts author --dry-run prompts/foo_python.prompt
      pdd contracts author --force prompts/foo_python.prompt
      pdd contracts author --formalize prompts/foo_python.prompt
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)
    verbose: bool = obj.get("verbose", False)
    strength: float = obj.get("strength", 0.5)
    temperature: float = obj.get("temperature", 0.1)
    time_val: Optional[float] = obj.get("time")

    result = author_contracts(
        Path(prompt_file),
        code_path=Path(code_file) if code_file else None,
        mode=mode,
        strength=strength,
        temperature=temperature,
        time=time_val,
        verbose=verbose,
        dry_run=dry_run,
        force=force,
        formalize=formalize,
    )

    if as_json:
        click.echo(_json.dumps(result.as_dict(), indent=2))
    else:
        _render_author_result(result, quiet=quiet)

    if result.error:
        raise click.exceptions.Exit(2)
    if result.skipped:
        raise click.exceptions.Exit(1)
