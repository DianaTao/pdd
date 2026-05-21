"""
pdd evidence — per-rule evidence reporting (deterministic, no LLM).

Top-level command group: pdd evidence emit | validate | show
"""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..evidence_manifest import (
    EvidenceManifest,
    ManifestValidation,
    RuleEvidence,
    SCHEMA,
    build_manifest,
    emit_manifest,
    validate_manifest,
)

_console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _render_manifest(manifest: EvidenceManifest, *, gap_only: bool = False, quiet: bool = False) -> None:
    """Print a rule-by-rule evidence report."""
    if not quiet:
        _console.print(
            f"[bold]{escape(manifest.prompt_path)}[/bold]  "
            f"[cyan]{manifest.rule_count} rules[/cyan]  "
            f"[{'red' if manifest.gap_count else 'green'}]{manifest.gap_count} gap(s)[/]"
        )

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("rule", width=8)
    table.add_column("status", width=14)
    table.add_column("stories", width=6, justify="right")
    table.add_column("tests", width=6, justify="right")
    table.add_column("formal", width=6, justify="right")
    table.add_column("gap", width=5)

    for rule in manifest.rules:
        if gap_only and not rule.gap:
            continue
        gap_cell = "[red]yes[/red]" if rule.gap else "[green]no[/green]"
        status_style = "yellow" if rule.gap else "green"
        table.add_row(
            escape(rule.rule_id),
            f"[{status_style}]{escape(rule.status)}[/{status_style}]",
            str(len(rule.stories)),
            str(len(rule.tests)),
            str(len(rule.formal)),
            gap_cell,
        )

    _console.print(table)

    # Print snippets for gap rules
    for rule in manifest.rules:
        if not rule.gap:
            continue
        _console.print(f"\n  [bold magenta]{escape(rule.rule_id)}[/bold magenta] — gap")
        if rule.tests:
            _console.print(f"    tests: {', '.join(escape(t) for t in rule.tests[:5])}")
        if rule.story_snippets:
            for snippet in rule.story_snippets[:1]:
                _console.print(f"    story excerpt: [dim italic]{escape(snippet[:200])}[/dim italic]")


def _render_validation(val: ManifestValidation, *, quiet: bool = False) -> None:
    """Print manifest validation result."""
    if val.valid:
        if not quiet:
            _console.print(f"[green]✓ valid[/green]  {escape(val.path)}  schema={escape(val.schema)}")
    else:
        _console.print(f"[red]✗ invalid[/red]  {escape(val.path)}")
        for err in val.errors:
            _console.print(f"  [red]error:[/red] {escape(err)}")


# ---------------------------------------------------------------------------
# Click group and subcommands
# ---------------------------------------------------------------------------

@click.group(name="evidence")
def evidence_group() -> None:
    """Evidence reporting for prompt contract rules (deterministic, no LLM)."""


@evidence_group.command("emit")
@click.argument("prompt_file", type=click.Path(exists=True))
@click.option("--stories-dir", "stories_dir", type=click.Path(exists=True, file_okay=False), default=None)
@click.option("--tests-dir", "tests_dir", type=click.Path(exists=True, file_okay=False), default=None)
@click.option("--output", "output_path", type=click.Path(), default=None,
              help="Write manifest JSON to this path (default: print only).")
@click.option("--json", "as_json", is_flag=True, default=False, help="Print manifest JSON to stdout.")
@click.option("--gap-only", is_flag=True, default=False, help="Only show rules with evidence gaps.")
@click.option("--markdown", is_flag=True, default=False, help="Output a markdown report for PR comments.")
@click.pass_context
def evidence_emit(
    ctx: click.Context,
    prompt_file: str,
    stories_dir: Optional[str],
    tests_dir: Optional[str],
    output_path: Optional[str],
    as_json: bool,
    gap_only: bool,
    markdown: bool,
) -> None:
    """Build and display a per-rule evidence manifest.

    \b
    Examples:
      pdd evidence emit prompts/foo_python.prompt
      pdd evidence emit --gap-only prompts/foo_python.prompt
      pdd evidence emit --json prompts/foo_python.prompt
      pdd evidence emit --markdown prompts/foo_python.prompt
      pdd evidence emit --output reports/evidence.json prompts/foo_python.prompt
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)

    out_path = Path(output_path) if output_path else None
    manifest = emit_manifest(
        Path(prompt_file),
        stories_dir=Path(stories_dir) if stories_dir else None,
        tests_dir=Path(tests_dir) if tests_dir else None,
        output_path=out_path,
    )

    if as_json:
        click.echo(_json.dumps(manifest.as_dict(), indent=2))
    elif markdown:
        _print_markdown(manifest, gap_only=gap_only)
    else:
        _render_manifest(manifest, gap_only=gap_only, quiet=quiet)

    if out_path and not quiet:
        _console.print(f"  [dim]wrote {out_path}[/dim]")


def _print_markdown(manifest: EvidenceManifest, *, gap_only: bool = False) -> None:
    """Print a markdown evidence report suitable for PR comments."""
    lines = [
        f"## Evidence report — `{manifest.prompt_path}`",
        "",
        f"**{manifest.rule_count} rules** | **{manifest.gap_count} gap(s)**",
        "",
        "| Rule | Status | Stories | Tests | Formal | Gap |",
        "|------|--------|---------|-------|--------|-----|",
    ]
    for rule in manifest.rules:
        if gap_only and not rule.gap:
            continue
        gap_str = "⚠️" if rule.gap else "✅"
        lines.append(
            f"| {rule.rule_id} | {rule.status} | {len(rule.stories)} | "
            f"{len(rule.tests)} | {len(rule.formal)} | {gap_str} |"
        )
    lines.append("")
    if manifest.gap_count:
        lines.append("### Gap details")
        for rule in manifest.rules:
            if not rule.gap:
                continue
            lines.append(f"\n**{rule.rule_id}** ({rule.status})")
            if rule.tests:
                lines.append(f"- tests: {', '.join(f'`{t}`' for t in rule.tests[:5])}")
            if not rule.stories:
                lines.append("- ⚠️ no linked story")
            if not rule.tests:
                lines.append("- ⚠️ no linked test")
    click.echo("\n".join(lines))


@evidence_group.command("validate")
@click.argument("manifest_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, default=False)
@click.pass_context
def evidence_validate(
    ctx: click.Context,
    manifest_file: str,
    as_json: bool,
) -> None:
    """Validate a stored evidence manifest JSON file.

    \b
    Examples:
      pdd evidence validate reports/evidence.json
      pdd evidence validate --json reports/evidence.json
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)

    val = validate_manifest(Path(manifest_file))

    if as_json:
        click.echo(_json.dumps(val.as_dict(), indent=2))
    else:
        _render_validation(val, quiet=quiet)

    if not val.valid:
        raise click.exceptions.Exit(2)


@evidence_group.command("show")
@click.argument("manifest_file", type=click.Path(exists=True))
@click.option("--gap-only", is_flag=True, default=False, help="Show only gap rules.")
@click.option("--markdown", is_flag=True, default=False)
@click.option("--json", "as_json", is_flag=True, default=False)
@click.pass_context
def evidence_show(
    ctx: click.Context,
    manifest_file: str,
    gap_only: bool,
    markdown: bool,
    as_json: bool,
) -> None:
    """Display a previously emitted evidence manifest.

    \b
    Examples:
      pdd evidence show reports/evidence.json
      pdd evidence show --gap-only reports/evidence.json
      pdd evidence show --markdown reports/evidence.json
    """
    obj = ctx.obj or {}
    quiet: bool = obj.get("quiet", False)

    try:
        import json as _stdlib_json  # pylint: disable=import-outside-toplevel
        data = _stdlib_json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as exc:
        _console.print(f"[red]Cannot read manifest: {exc}[/red]")
        raise click.exceptions.Exit(2) from exc

    # Reconstruct EvidenceManifest from dict
    rules = [
        RuleEvidence(
            rule_id=r["rule_id"],
            status=r["status"],
            stories=r.get("stories", []),
            story_snippets=r.get("story_snippets", []),
            tests=r.get("tests", []),
            formal=r.get("formal", []),
            waiver=r.get("waiver"),
            gap=r.get("gap", False),
        )
        for r in data.get("rules", [])
    ]
    manifest = EvidenceManifest(
        schema=data.get("schema", SCHEMA),
        generated_at=data.get("generated_at", ""),
        prompt_path=data.get("prompt_path", manifest_file),
        prompt_sha256=data.get("prompt_sha256", ""),
        rule_count=data.get("rule_count", len(rules)),
        rules=rules,
        gap_count=data.get("gap_count", sum(1 for r in rules if r.gap)),
    )

    if as_json:
        click.echo(_json.dumps(manifest.as_dict(), indent=2))
    elif markdown:
        _print_markdown(manifest, gap_only=gap_only)
    else:
        _render_manifest(manifest, gap_only=gap_only, quiet=quiet)
