"""
Regression tests for the ``pdd checkup contract check`` CLI help path.

These tests pin the canonical help-path documented in ``docs/contract_check.md``:

    pdd checkup contract check --help

It must exit 0 and render the help for the ``check`` subcommand. A previous
regression (tracked in issue #5) showed the path exiting 2 with a doubled
``check check`` in the Usage line, caused by registering a subcommand against
a ``click.Command`` instead of a ``click.Group``.

Note: until the upstream ``codex/pr-1122-contracts-check`` PR is merged, the
``contract`` subgroup is not registered on this fork — these tests will
fail-red against that intermediate state. That is the intended behavior: the
regression guard is encoded here so that any future re-introduction of the
double-``check`` bug is caught immediately.
"""
from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from pdd.commands.checkup import checkup


def _contract_subgroup_present() -> bool:
    """Return True iff ``checkup`` is a Group with a ``contract`` subgroup registered.

    Until the upstream ``codex/pr-1122-contracts-check`` PR is merged on this
    fork, ``checkup`` is a bare ``click.Command`` and the structural assertions
    cannot be evaluated meaningfully. Tests that depend on the post-fix tree
    use this helper to skip with a clear reason.
    """
    if not isinstance(checkup, click.Group):
        return False
    return checkup.get_command(ctx=None, cmd_name="contract") is not None


class TestCheckupContractCheckHelpPath:
    """Pin the canonical ``pdd checkup contract check --help`` help path."""

    def test_help_path_exits_zero(self) -> None:
        """``checkup contract check --help`` must exit 0.

        Regression for issue #5: the path used to exit 2 with
        ``Missing argument 'TARGET'`` because ``check`` was registered as a
        subcommand of itself.
        """
        runner = CliRunner()
        result = runner.invoke(
            checkup,
            ["contract", "check", "--help"],
            obj={"quiet": True, "verbose": False},
        )
        assert result.exit_code == 0, (
            f"Expected exit 0 for `checkup contract check --help`, "
            f"got {result.exit_code}.\nOutput:\n{result.output}"
        )

    def test_help_path_usage_line_has_no_doubled_check(self) -> None:
        """The Usage line must not contain ``check check`` (Click misregistration symptom)."""
        runner = CliRunner()
        result = runner.invoke(
            checkup,
            ["contract", "check", "--help"],
            obj={"quiet": True, "verbose": False},
        )
        # Find the Usage: line and assert no doubled subcommand name.
        usage_lines = [
            line for line in result.output.splitlines()
            if line.lstrip().startswith("Usage:")
        ]
        assert usage_lines, (
            f"No 'Usage:' line found in help output:\n{result.output}"
        )
        for line in usage_lines:
            assert "check check" not in line, (
                f"Usage line contains doubled 'check check' "
                f"(subcommand-on-Command misregistration):\n{line}"
            )

    def test_help_path_renders_check_command_help(self) -> None:
        """The rendered help must be the ``check`` command's help (TARGET argument visible)."""
        runner = CliRunner()
        result = runner.invoke(
            checkup,
            ["contract", "check", "--help"],
            obj={"quiet": True, "verbose": False},
        )
        # The check subcommand is documented to take a TARGET argument.
        # If we get the right command's help, TARGET should appear in the body.
        assert "TARGET" in result.output, (
            f"Expected 'TARGET' argument in rendered help output, "
            f"but it was missing.\nOutput:\n{result.output}"
        )

    @pytest.mark.skipif(
        not _contract_subgroup_present(),
        reason=(
            "`checkup contract` subgroup is not registered on this fork yet — "
            "skipped until upstream `codex/pr-1122-contracts-check` is merged. "
            "Once present, this guard asserts the Click tree is wired as Groups "
            "(not bare Commands), preventing the doubled `check check` Usage "
            "regression."
        ),
    )
    def test_contract_subgroup_is_a_click_group(self) -> None:
        """``checkup contract`` must be a Click Group, not a bare Command.

        This guards the structural root-cause: a sibling-subcommand cannot be
        registered against a ``click.Command`` instance. The fix requires
        ``contract`` (and ``checkup``) to be promoted to ``click.Group``.
        """
        # Walk the Click command tree: checkup -> contract -> check
        assert isinstance(checkup, click.Group), (
            "Expected `checkup` to be a click.Group so that subgroups "
            "like `contract` can hang off it."
        )
        contract = checkup.get_command(ctx=None, cmd_name="contract")
        assert contract is not None, (
            "`contract` subgroup is not registered on `checkup`."
        )
        assert isinstance(contract, click.Group), (
            f"Expected `checkup contract` to be a click.Group, "
            f"got {type(contract).__name__}. A bare Command here is what "
            f"produces the doubled `check check` Usage line."
        )
        check_cmd = contract.get_command(ctx=None, cmd_name="check")
        assert check_cmd is not None, (
            "`check` subcommand is not registered on `checkup contract`."
        )
