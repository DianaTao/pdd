"""
Coverage command.
"""
import click
from pathlib import Path
from typing import Optional

from ..core.errors import handle_error


@click.command("coverage")
@click.option(
    "--contracts",
    is_flag=True,
    default=False,
    help="Cross-reference module prompts against user stories to identify coverage gaps.",
)
@click.option(
    "--prompts-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory containing prompt files.",
)
@click.option(
    "--stories-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory containing user story files.",
)
@click.option(
    "--tests-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory containing test files.",
)
@click.option(
    "--quiet",
    is_flag=True,
    default=False,
    help="Decrease output verbosity for minimal information.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Increase output verbosity for more detailed information.",
)
@click.pass_context
def coverage(
    ctx: click.Context,
    contracts: bool,
    prompts_dir: Optional[Path],
    stories_dir: Optional[Path],
    tests_dir: Optional[Path],
    quiet: bool,
    verbose: bool,
):
    """
    Project coverage diagnostics.
    """
    if not contracts:
        click.echo("Usage: pdd coverage --contracts")
        return

    from pathlib import Path
    
    # Default directories
    p_dir = prompts_dir or Path("pdd/prompts")
    s_dir = stories_dir or Path("user_stories")
    t_dir = tests_dir or Path("tests")

    try:
        from ..coverage_contracts import run_coverage_contracts_cli

        run_coverage_contracts_cli(
            prompts_dir=p_dir,
            stories_dir=s_dir,
            tests_dir=t_dir,
            quiet=quiet or ctx.obj.get("quiet", False),
            verbose=verbose or ctx.obj.get("verbose", False),
        )
    except click.exceptions.Exit:
        raise
    except Exception as e:
        handle_error(e, "coverage", ctx.obj.get("quiet", False))
        raise click.exceptions.Exit(1)
