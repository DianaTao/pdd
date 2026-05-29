"""
Tests for pdd.commands.maintenance module.

Tests cover:
- sync command: basic invocation, dry-run, deprecated --log, GitHub issue URL dispatch,
  one-session defaults, error handling (Abort, generic exceptions), durable mode constraints,
  target-coverage types.
- sync-architecture command: basic invocation, dry-run, report rendering, nearest ancestor project resolution,
  validation failure reporting.
- auto-deps command: basic invocation, new options (include-docs, no-dedup, concurrency),
  quote stripping, error handling.
- setup command: install_completion + setup utility flow, error handling.
- _run_agentic_sync_dispatch: success, failure (Exit(1)), quiet mode, exception handling.
- _run_global_sync_dispatch: success, failure, exception handling.
- _resolve_global_sync_budget and _resolve_global_sync_target_coverage: .pddrc resolution.
- _echo_architecture_sync_result: all warning types and error states.
"""

import pytest
import json
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from click.testing import CliRunner
import click

from pdd.commands.maintenance import (
    sync, 
    sync_architecture, 
    auto_deps, 
    setup, 
    _run_agentic_sync_dispatch,
    _run_global_sync_dispatch,
    _resolve_global_sync_budget,
    _resolve_global_sync_target_coverage,
    _echo_architecture_sync_result
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def base_ctx_obj():
    """Standard ctx.obj dict for CLI tests."""
    return {
        "strength": 0.5,
        "temperature": 0.0,
        "time": 0.25,
        "verbose": False,
        "force": True,
        "quiet": False,
        "output_cost": None,
        "review_examples": False,
        "local": True,
        "context": None,
    }


def _make_cli(command, ctx_obj):
    """Build a throwaway Click group with the given command attached."""
    @click.group()
    @click.pass_context
    def cli(ctx):
        ctx.ensure_object(dict)
        ctx.obj = dict(ctx_obj)  # copy to avoid cross-test pollution
    cli.add_command(command)
    return cli


# ---------------------------------------------------------------------------
# sync command tests
# ---------------------------------------------------------------------------

class TestSyncCommand:

    def test_sync_basic(self, runner, base_ctx_obj):
        """sync dispatches to sync_main with correct arguments."""
        mock_result = ({"success": True}, 0.05, "gpt-4")
        cli = _make_cli(sync, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_main", return_value=mock_result) as mock_sm:
            result = runner.invoke(cli, [
                "sync", "my_module",
                "--max-attempts", "5",
                "--budget", "15.0",
                "--skip-verify",
                "--skip-tests",
                "--target-coverage", "85.0",
                "--no-steer",
            ], catch_exceptions=False)

            assert result.exit_code == 0
            mock_sm.assert_called_once()
            kw = mock_sm.call_args.kwargs
            assert kw["basename"] == "my_module"
            assert kw["max_attempts"] == 5
            assert kw["budget"] == 15.0
            assert kw["skip_verify"] is True
            assert kw["skip_tests"] is True
            assert kw["target_coverage"] == 85.0
            assert kw["no_steer"] is True
            # one_session defaults to False for non-URL
            assert kw["one_session"] is False

    def test_sync_dry_run(self, runner, base_ctx_obj):
        """sync --dry-run forwards dry_run=True to sync_main."""
        mock_result = ({"dry_run": True}, 0.0, "none")
        cli = _make_cli(sync, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_main", return_value=mock_result) as mock_sm:
            result = runner.invoke(cli, ["sync", "calc", "--dry-run"], catch_exceptions=False)
            assert result.exit_code == 0
            assert mock_sm.call_args.kwargs["dry_run"] is True

    def test_sync_without_basename_dispatches_global_sync(
        self,
        runner,
        base_ctx_obj,
    ):
        """No-argument sync uses global sync."""
        cli = _make_cli(sync, base_ctx_obj)
        mock_result = ("global done", 0.0, "none")

        with patch(
            "pdd.commands.maintenance._run_global_sync_dispatch",
            return_value=mock_result,
        ) as mock_global, \
             patch("pdd.commands.maintenance.run_agentic_sync") as mock_agentic:
            result = runner.invoke(cli, ["sync"], catch_exceptions=False)

        assert result.exit_code == 0
        mock_global.assert_called_once()
        mock_agentic.assert_not_called()
        assert mock_global.call_args.kwargs["one_session"] is False

    def test_sync_without_basename_forwards_global_local_flag(
        self,
        runner,
        base_ctx_obj,
    ):
        """Top-level --local must be preserved when global sync dispatches."""
        base_ctx_obj["local"] = True
        cli = _make_cli(sync, base_ctx_obj)
        mock_result = ("global done", 0.0, "none")

        with patch(
            "pdd.commands.maintenance._run_global_sync_dispatch",
            return_value=mock_result,
        ) as mock_global:
            result = runner.invoke(cli, ["sync"], catch_exceptions=False)

        assert result.exit_code == 0
        # The local flag is in ctx.obj, which _run_global_sync_dispatch uses
        assert mock_global.call_args.kwargs["ctx"].obj["local"] is True

    def test_sync_deprecated_log_flag(self, runner, base_ctx_obj):
        """--log emits a deprecation warning and sets dry_run=True."""
        mock_result = ({"dry_run": True}, 0.0, "none")
        cli = _make_cli(sync, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_main", return_value=mock_result) as mock_sm:
            result = runner.invoke(cli, ["sync", "calc", "--log"], catch_exceptions=False)
            assert result.exit_code == 0
            assert "deprecated" in result.output.lower() or "deprecated" in (result.stderr or "").lower()
            assert mock_sm.call_args.kwargs["dry_run"] is True

    def test_sync_github_url_dispatches_to_agentic(self, runner, base_ctx_obj):
        """When basename is a GitHub URL, sync dispatches to run_agentic_sync."""
        base_ctx_obj["context"] = "backend"
        cli = _make_cli(sync, base_ctx_obj)
        mock_agentic = (True, "synced 2 modules", 0.30, "claude-3")

        with patch("pdd.commands.maintenance._is_github_issue_url", return_value=True), \
             patch("pdd.commands.maintenance.run_agentic_sync", return_value=mock_agentic) as mock_ras:
            result = runner.invoke(cli, [
                "sync",
                "https://github.com/org/repo/issues/99",
                "--timeout-adder", "10.0",
                "--no-github-state",
            ], catch_exceptions=False)

            assert result.exit_code == 0
            mock_ras.assert_called_once()
            kw = mock_ras.call_args.kwargs
            assert kw["issue_url"] == "https://github.com/org/repo/issues/99"
            assert kw["timeout_adder"] == 10.0
            assert kw["use_github_state"] is False
            # one_session defaults to True for agentic sync
            assert kw["one_session"] is True
            assert kw["durable"] is False
            assert kw["durable_branch"] is None
            assert kw["no_resume"] is False
            assert kw["durable_max_parallel"] is None
            assert kw["strength"] == base_ctx_obj["strength"]
            assert kw["temperature"] == base_ctx_obj["temperature"]
            assert kw["context_override"] == base_ctx_obj["context"]

    def test_sync_github_url_failure_exits_1(self, runner, base_ctx_obj):
        """Agentic sync returning success=False raises Exit(1)."""
        cli = _make_cli(sync, base_ctx_obj)
        mock_agentic = (False, "module auth failed", 0.10, "gpt-4")

        with patch("pdd.commands.maintenance._is_github_issue_url", return_value=True), \
             patch("pdd.commands.maintenance.run_agentic_sync", return_value=mock_agentic):
            result = runner.invoke(cli, [
                "sync", "https://github.com/org/repo/issues/1",
            ])
            assert result.exit_code == 1

    def test_sync_github_url_forwards_durable_flags(self, runner, base_ctx_obj):
        """Durable issue-sync flags are forwarded to run_agentic_sync."""
        cli = _make_cli(sync, base_ctx_obj)
        mock_agentic = (True, "ok", 0.10, "gpt-4")

        with patch("pdd.commands.maintenance._is_github_issue_url", return_value=True), \
             patch("pdd.commands.maintenance.run_agentic_sync", return_value=mock_agentic) as mock_ras:
            result = runner.invoke(cli, [
                "sync",
                "https://github.com/org/repo/issues/5",
                "--durable",
                "--durable-branch",
                "sync/custom",
                "--no-resume",
                "--durable-max-parallel",
                "2",
            ], catch_exceptions=False)

            assert result.exit_code == 0
            kw = mock_ras.call_args.kwargs
            assert kw["durable"] is True
            assert kw["durable_branch"] == "sync/custom"
            assert kw["no_resume"] is True
            assert kw["durable_max_parallel"] == 2

    def test_sync_durable_requires_github_issue_url(self, runner, base_ctx_obj):
        """Durable flags are rejected for single-module sync."""
        cli = _make_cli(sync, base_ctx_obj)

        result = runner.invoke(cli, ["sync", "module", "--durable"])

        assert result.exit_code != 0
        assert "GitHub issue URL" in result.output

    def test_sync_durable_branch_requires_durable_mode(self, runner, base_ctx_obj):
        """Durable configuration flags are not silently ignored."""
        cli = _make_cli(sync, base_ctx_obj)

        with patch("pdd.commands.maintenance._is_github_issue_url", return_value=True):
            result = runner.invoke(cli, [
                "sync",
                "https://github.com/org/repo/issues/5",
                "--durable-branch",
                "sync/custom",
            ])

        assert result.exit_code != 0
        assert "require --durable" in result.output

    def test_sync_abort_reraised(self, runner, base_ctx_obj):
        """click.Abort from sync_main is re-raised, not caught by handle_error."""
        cli = _make_cli(sync, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_main", side_effect=click.Abort()), \
             patch("pdd.commands.maintenance.handle_error") as mock_he:
            result = runner.invoke(cli, ["sync", "mod"])
            assert result.exit_code != 0
            mock_he.assert_not_called()

    def test_sync_exception_handled(self, runner, base_ctx_obj):
        """sync calls handle_error on generic exception."""
        cli = _make_cli(sync, base_ctx_obj)
        with patch("pdd.commands.maintenance.sync_main", side_effect=ValueError("fail")), \
             patch("pdd.commands.maintenance.handle_error") as mock_he:
            result = runner.invoke(cli, ["sync", "mod"])
            mock_he.assert_called_once()
            assert result.exit_code == 0
            assert result.output == ""

    def test_sync_has_track_cost_decorator(self):
        """Verify sync command uses @track_cost decorator."""
        # Click commands have a callback that is the original function wrapped by Click and others
        assert hasattr(sync.callback, '__wrapped__'), "sync should have @track_cost decorator"

    def test_sync_with_no_target_coverage_does_not_raise_typeerror(self, runner, base_ctx_obj):
        """Issue #194: pdd sync without --target-coverage should not raise TypeError."""
        mock_result = ('success', 0.5, 'model')
        cli = _make_cli(sync, base_ctx_obj)
        with patch("pdd.commands.maintenance.sync_main", return_value=mock_result) as mock_sm:
            result = runner.invoke(cli, ["sync", "test_module"])
            assert result.exit_code == 0
            assert 'TypeError' not in result.output
            mock_sm.assert_called_once()

    def test_target_coverage_cli_option_converts_string_to_float(self, runner, base_ctx_obj):
        """Issue #194: --target-coverage '85.5' should be converted to float."""
        mock_result = ('success', 0.5, 'model')
        cli = _make_cli(sync, base_ctx_obj)
        with patch("pdd.commands.maintenance.sync_main", return_value=mock_result) as mock_sm:
            result = runner.invoke(cli, ["sync", "test_module", "--target-coverage", "85.5"])
            assert result.exit_code == 0
            call_kwargs = mock_sm.call_args.kwargs
            assert isinstance(call_kwargs.get('target_coverage'), float)
            assert call_kwargs.get('target_coverage') == 85.5

# ---------------------------------------------------------------------------
# sync-architecture command tests
# ---------------------------------------------------------------------------

class TestSyncArchitectureCommand:

    def test_sync_architecture_basic(self, runner, base_ctx_obj):
        """sync-architecture dispatches to sync_prompts_to_architecture."""
        mock_result = {"success": True, "updated_count": 1, "skipped_count": 0}
        cli = _make_cli(sync_architecture, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_prompts_to_architecture", return_value=mock_result) as mock_spa:
            result = runner.invoke(cli, ["sync-architecture", "mod1.prompt"], catch_exceptions=False)
            assert result.exit_code == 0
            mock_spa.assert_called_once_with(filenames=["mod1.prompt"], dry_run=False)
            assert "Updated 1 module(s)" in result.output

    def test_sync_architecture_dry_run(self, runner, base_ctx_obj):
        """sync-architecture --dry-run forwards dry_run=True."""
        mock_result = {"success": True, "updated_count": 0, "skipped_count": 1}
        cli = _make_cli(sync_architecture, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_prompts_to_architecture", return_value=mock_result) as mock_spa:
            result = runner.invoke(cli, ["sync-architecture", "--dry-run"], catch_exceptions=False)
            assert result.exit_code == 0
            mock_spa.assert_called_once_with(filenames=None, dry_run=True)
            assert "Dry run:" in result.output

    def test_sync_architecture_failure_exits_1(self, runner, base_ctx_obj):
        """sync-architecture exits 1 on failure."""
        mock_result = {"success": False, "updated_count": 0, "skipped_count": 0}
        cli = _make_cli(sync_architecture, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_prompts_to_architecture", return_value=mock_result):
            result = runner.invoke(cli, ["sync-architecture"])
            assert result.exit_code == 1

    def test_sync_architecture_exception_handled(self, runner, base_ctx_obj):
        """sync-architecture handles generic exceptions."""
        cli = _make_cli(sync_architecture, base_ctx_obj)

        with patch("pdd.commands.maintenance.sync_prompts_to_architecture", side_effect=RuntimeError("boom")), \
             patch("pdd.commands.maintenance.handle_error") as mock_he:
            result = runner.invoke(cli, ["sync-architecture"])
            mock_he.assert_called_once()
            assert result.exit_code == 0 # returns None which results in exit 0 in this mock setup

    def test_sync_architecture_uses_nearest_cwd_project(self, runner, tmp_path, monkeypatch):
        """CLI should target the nearest ancestor project, not always the repo root."""
        from pdd.cli import cli as pdd_cli
        
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        root_prompts = repo_root / "prompts"
        root_prompts.mkdir()
        (root_prompts / "root_python.prompt").write_text("<pdd-reason>Updated root</pdd-reason>", encoding="utf-8")
        (repo_root / "architecture.json").write_text('[]', encoding="utf-8")

        nested_root = repo_root / "apps" / "nested"
        nested_root.mkdir(parents=True)
        (nested_root / "architecture.json").write_text('[]', encoding="utf-8")
        
        monkeypatch.chdir(nested_root)

        with patch("pdd.commands.maintenance.sync_prompts_to_architecture") as mock_spa:
            mock_spa.return_value = {"success": True, "updated_count": 0, "skipped_count": 0}
            result = runner.invoke(pdd_cli, ["sync-architecture"])
            assert result.exit_code == 0
            mock_spa.assert_called_once()

    def test_sync_architecture_exits_nonzero_on_validation_failure(self, runner, base_ctx_obj):
        """Validation failures should surface clearly and fail the command."""
        mock_result = {
            "success": False,
            "updated_count": 1,
            "skipped_count": 0,
            "results": [],
            "validation": {
                "valid": False,
                "errors": [{"message": "Module depends on non-existent module"}],
                "warnings": [],
            },
            "errors": [],
        }
        cli = _make_cli(sync_architecture, base_ctx_obj)
        with patch("pdd.commands.maintenance.sync_prompts_to_architecture", return_value=mock_result):
            result = runner.invoke(cli, ["sync-architecture"])
            assert result.exit_code == 1
            assert "Validation errors:" in result.output
            assert "depends on non-existent module" in result.output

# ---------------------------------------------------------------------------
# auto-deps command tests
# ---------------------------------------------------------------------------

class TestAutoDepsCommand:

    def test_auto_deps_basic(self, runner, base_ctx_obj, tmp_path):
        """auto-deps dispatches to auto_deps_main with correct arguments."""
        prompt = tmp_path / "test.prompt"
        prompt.write_text("prompt content")
        dep_dir = tmp_path / "deps"
        dep_dir.mkdir()

        mock_result = ("modified prompt", 0.03, "gpt-4")
        cli = _make_cli(auto_deps, base_ctx_obj)

        with patch("pdd.commands.maintenance.auto_deps_main", return_value=mock_result) as mock_adm:
            result = runner.invoke(cli, [
                "auto-deps",
                str(prompt),
                str(dep_dir),
                "--force-scan",
                "--include-docs",
                "--no-dedup",
                "--concurrency", "4",
            ], catch_exceptions=False)

            assert result.exit_code == 0
            mock_adm.assert_called_once()
            kw = mock_adm.call_args.kwargs
            assert kw["prompt_file"] == str(prompt)
            assert kw["directory_path"] == str(dep_dir)
            assert kw["force_scan"] is True
            assert kw["include_docs"] is True
            assert kw["no_dedup"] is True
            assert kw["concurrency"] == 4

    def test_auto_deps_strips_quotes(self, runner, base_ctx_obj, tmp_path):
        """Directory path with quotes is stripped."""
        prompt = tmp_path / "test.prompt"
        prompt.write_text("content")
        dep_dir = tmp_path / "deps"
        dep_dir.mkdir()

        mock_result = ("modified", 0.01, "gpt-4")
        cli = _make_cli(auto_deps, base_ctx_obj)

        # Pass path with surrounding quotes
        quoted_path = f'"{dep_dir}"'
        with patch("pdd.commands.maintenance.auto_deps_main", return_value=mock_result) as mock_adm:
            result = runner.invoke(cli, [
                "auto-deps", str(prompt), quoted_path,
            ], catch_exceptions=False)

            assert result.exit_code == 0
            kw = mock_adm.call_args.kwargs
            assert kw["directory_path"] == str(dep_dir)

    def test_auto_deps_has_track_cost_decorator(self):
        """Verify auto-deps command uses @track_cost decorator."""
        assert hasattr(auto_deps.callback, '__wrapped__'), "auto_deps should have @track_cost decorator"

    def test_auto_deps_exception_handled(self, runner, base_ctx_obj, tmp_path):
        """auto-deps handles generic exceptions."""
        prompt = tmp_path / "test.prompt"
        prompt.write_text("content")
        cli = _make_cli(auto_deps, base_ctx_obj)
        with patch("pdd.commands.maintenance.auto_deps_main", side_effect=RuntimeError("fail")), \
             patch("pdd.commands.maintenance.handle_error") as mock_he:
            result = runner.invoke(cli, ["auto-deps", str(prompt), "."])
            mock_he.assert_called_once()
            assert result.exit_code == 0

# ---------------------------------------------------------------------------
# setup command tests
# ---------------------------------------------------------------------------

class TestSetupCommand:

    def test_setup_calls_both_functions(self, runner):
        """setup calls install_completion then _run_setup_utility."""
        cli = _make_cli(setup, {"quiet": False})

        with patch("pdd.cli.install_completion") as mock_ic, \
             patch("pdd.commands.maintenance._run_setup_utility") as mock_su:
            result = runner.invoke(cli, ["setup"], catch_exceptions=False)

            assert result.exit_code == 0
            mock_ic.assert_called_once_with(quiet=False)
            mock_su.assert_called_once()

    def test_setup_error_handled(self, runner):
        """Exceptions in setup are caught by handle_error."""
        cli = _make_cli(setup, {"quiet": False})

        with patch("pdd.cli.install_completion", side_effect=RuntimeError("fail")), \
             patch("pdd.commands.maintenance.handle_error") as mock_he:
            result = runner.invoke(cli, ["setup"])
            mock_he.assert_called_once()
            assert isinstance(mock_he.call_args[0][0], RuntimeError)
            assert mock_he.call_args[0][1] == "setup"

    def test_setup_abort_handled(self, runner):
        """click.Abort in setup is re-raised."""
        cli = _make_cli(setup, {"quiet": False})

        with patch("pdd.cli.install_completion", side_effect=click.Abort()):
            result = runner.invoke(cli, ["setup"])
            assert result.exit_code != 0

# ---------------------------------------------------------------------------
# Internal dispatcher and helper tests
# ---------------------------------------------------------------------------

class TestInternalHelpers:

    def test_run_agentic_sync_dispatch_success(self, capsys):
        """_run_agentic_sync_dispatch success path."""
        ctx = click.Context(click.Command("sync"), obj={"quiet": False})
        mock_res = (True, "Agentic sync done", 0.1, "gpt-4")
        with ctx.scope(), patch("pdd.commands.maintenance.run_agentic_sync", return_value=mock_res):
            res = _run_agentic_sync_dispatch(ctx, issue_url="http://github.com/a/b/issues/1")
            assert res == ("Agentic sync done", 0.1, "gpt-4")
            out = capsys.readouterr().out
            assert "Status: Success" in out

    def test_run_agentic_sync_dispatch_failure(self):
        """_run_agentic_sync_dispatch failure raises Exit(1)."""
        ctx = click.Context(click.Command("sync"), obj={"quiet": False})
        mock_res = (False, "Agentic sync failed", 0.1, "gpt-4")
        with ctx.scope(), patch("pdd.commands.maintenance.run_agentic_sync", return_value=mock_res):
            with pytest.raises(click.exceptions.Exit) as exc:
                _run_agentic_sync_dispatch(ctx, issue_url="http://github.com/a/b/issues/1")
            assert exc.value.exit_code == 1

    def test_run_agentic_sync_dispatch_exception(self):
        """_run_agentic_sync_dispatch handles exceptions."""
        ctx = click.Context(click.Command("sync"), obj={"quiet": False})
        with ctx.scope(), patch("pdd.commands.maintenance.run_agentic_sync", side_effect=RuntimeError("boom")), \
             patch("pdd.commands.maintenance.handle_error") as mock_he:
            res = _run_agentic_sync_dispatch(ctx, issue_url="http://github.com/a/b/issues/1")
            assert res is None
            mock_he.assert_called_once()

    def test_run_agentic_sync_dispatch_reasoning_time(self):
        """_run_agentic_sync_dispatch passes reasoning_time when time_explicit is True."""
        ctx = click.Context(click.Command("sync"), obj={"quiet": True, "time": 0.5, "time_explicit": True})
        mock_res = (True, "done", 0.1, "gpt-4")
        with ctx.scope(), patch("pdd.commands.maintenance.run_agentic_sync", return_value=mock_res) as mock_ras:
            _run_agentic_sync_dispatch(ctx, issue_url="http://github.com/a/b/issues/1")
            assert mock_ras.call_args.kwargs["reasoning_time"] == 0.5

    def test_run_global_sync_dispatch_success(self, capsys):
        """_run_global_sync_dispatch success path."""
        ctx = click.Context(click.Command("sync"), obj={"quiet": False})
        mock_res = (True, "Global sync done", 0.1, "gpt-4")
        with ctx.scope(), patch("pdd.commands.maintenance.run_global_sync", return_value=mock_res):
            res = _run_global_sync_dispatch(ctx, budget=10.0)
            assert res == ("Global sync done", 0.1, "gpt-4")
            out = capsys.readouterr().out
            assert "Status: Success" in out

    def test_run_global_sync_dispatch_failure(self):
        """_run_global_sync_dispatch failure raises Exit(1)."""
        ctx = click.Context(click.Command("sync"), obj={"quiet": False})
        mock_res = (False, "Global sync failed", 0.1, "gpt-4")
        with ctx.scope(), patch("pdd.commands.maintenance.run_global_sync", return_value=mock_res):
            with pytest.raises(click.exceptions.Exit) as exc:
                _run_global_sync_dispatch(ctx, budget=10.0)
            assert exc.value.exit_code == 1

    def test_run_global_sync_dispatch_exception(self):
        """_run_global_sync_dispatch handles exceptions."""
        ctx = click.Context(click.Command("sync"), obj={"quiet": False})
        with ctx.scope(), patch("pdd.commands.maintenance.run_global_sync", side_effect=RuntimeError("boom")), \
             patch("pdd.commands.maintenance.handle_error") as mock_he:
            with pytest.raises(click.exceptions.Exit) as exc:
                _run_global_sync_dispatch(ctx, budget=10.0)
            assert exc.value.exit_code == 1
            mock_he.assert_called_once()

    def test_resolve_global_sync_budget_pddrc(self, tmp_path, monkeypatch):
        """_resolve_global_sync_budget resolves from .pddrc."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pddrc").write_text("version: '1.0'\ncontexts:\n  default:\n    defaults:\n      budget: 12.3", encoding="utf-8")
        assert _resolve_global_sync_budget(None) == 12.3

    def test_resolve_global_sync_budget_invalid_pddrc(self, tmp_path, monkeypatch):
        """_resolve_global_sync_budget falls back on invalid .pddrc."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pddrc").write_text("malformed", encoding="utf-8")
        assert _resolve_global_sync_budget(None) == 20.0

    def test_resolve_global_sync_budget_invalid_value(self, tmp_path, monkeypatch):
        """_resolve_global_sync_budget handles ValueError during float conversion."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pddrc").write_text("version: '1.0'\ncontexts:\n  default:\n    defaults:\n      budget: 'not-a-float'", encoding="utf-8")
        assert _resolve_global_sync_budget(None) == 20.0

    def test_resolve_global_sync_target_coverage_pddrc(self, tmp_path, monkeypatch):
        """_resolve_global_sync_target_coverage resolves from .pddrc."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pddrc").write_text("version: '1.0'\ncontexts:\n  default:\n    defaults:\n      target_coverage: 75.0", encoding="utf-8")
        assert _resolve_global_sync_target_coverage(None) == 75.0

    def test_resolve_global_sync_target_coverage_none(self, tmp_path, monkeypatch):
        """_resolve_global_sync_target_coverage returns None if not found."""
        monkeypatch.chdir(tmp_path)
        assert _resolve_global_sync_target_coverage(None) is None

    def test_resolve_global_sync_target_coverage_invalid_value(self, tmp_path, monkeypatch):
        """_resolve_global_sync_target_coverage handles ValueError during float conversion."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".pddrc").write_text("version: '1.0'\ncontexts:\n  default:\n    defaults:\n      target_coverage: 'not-a-float'", encoding="utf-8")
        assert _resolve_global_sync_target_coverage(None) is None

    def test_echo_architecture_sync_result_full(self, capsys):
        """_echo_architecture_sync_result renders all warning and error types."""
        result = {
            "updated_count": 1,
            "skipped_count": 1,
            "total_rules": 10,
            "total_stories": 5,
            "results": [
                {
                    "filename": "updated.prompt",
                    "updated": True,
                    "contract_summary": {
                        "rules": [1, 2],
                        "stories": [1],
                        "evidence_status": "stale"
                    }
                },
                {
                    "filename": "missing.prompt",
                    "updated": True,
                    "contract_summary": {
                        "rules": [],
                        "stories": [],
                        "evidence_status": "missing"
                    }
                },
                {
                    "filename": "failed.prompt",
                    "updated": False,
                    "success": False,
                    "error": "Reason"
                }
            ],
            "errors": ["Global Error"],
            "validation": {
                "errors": [{"message": "Val Error"}],
                "warnings": [{"message": "Val Warning"}]
            }
        }
        _echo_architecture_sync_result(result, dry_run=False)
        out = capsys.readouterr().out
        assert "Updated 1 module(s)" in out
        assert "Total Contracts: 10 rules, 5 stories" in out
        assert "Warning: Evidence is STALE for updated.prompt" in out
        assert "Warning: Evidence is MISSING for missing.prompt" in out
        assert "ERROR failed.prompt: Reason" in out
        assert "Sync errors:" in out
        assert "- Global Error" in out
        assert "Validation errors:" in out
        assert "- Val Error" in out
        assert "Validation warnings:" in out
        assert "- Val Warning" in out

    def test_echo_architecture_sync_result_dry_run(self, capsys):
        """_echo_architecture_sync_result dry run message."""
        _echo_architecture_sync_result({"updated_count": 1, "skipped_count": 1}, dry_run=True)
        assert "Dry run: would update 1 module(s)" in capsys.readouterr().out
