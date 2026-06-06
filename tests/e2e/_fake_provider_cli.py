"""Subprocess entrypoint: run the REAL ``pdd`` CLI with only the model/provider
boundary stubbed, for deterministic end-to-end prompt-gate validation (PR #1428).

This lets reviewers (and CI) exercise the automatic prompt gate through an actual
``python ... pdd ...`` process with a genuine OS exit code, against a disposable
fixture project, without any network or model credentials.

What runs FOR REAL (never mocked):
  * the ``pdd change`` / ``pdd generate`` Click command bodies,
  * ``pdd.change_main.change_main`` (orchestration + prompt save),
  * ``pdd.prompt_gate.maybe_run_workflow_prompt_gate`` and the gate it drives,
  * gate-mode resolution from ``.pddrc`` / ``pyproject.toml``,
  * the ``pdd.prompt_source_set_report.v1`` source-set report.

What is stubbed (the model/provider + pure path/config plumbing only):
  * ``pdd.change_main.change_func``              — the LLM call inside ``pdd change``;
  * ``pdd.change_main.construct_paths``          — path resolution → real file contents;
  * ``pdd.change_main.resolve_effective_config`` — deterministic strength/temp/time;
  * ``pdd.agentic_architecture.run_agentic_architecture`` — the model-backed prompt
    writer inside ``pdd generate`` (it normally shells out to an agentic CLI).

Behaviour is driven entirely by environment variables so the parent process owns
the fixture. Invoke as::

    python tests/e2e/_fake_provider_cli.py <pdd args...>

e.g. ``python tests/e2e/_fake_provider_cli.py change --manual c.prompt m.py in.prompt
--output out_python.prompt``. Everything after the script path is forwarded to the
real CLI verbatim.
"""
from __future__ import annotations

import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

# The deterministic "model" identity surfaced in CLI output / cost lines.
_FAKE_MODEL = "fake-e2e-model"


def _fake_change_func(
    change_prompt_content,
    input_code_content,
    input_prompt_content,
    strength,
    temperature,
    *,
    time,
    budget,
    verbose,
):
    """Stand in for the LLM in ``pdd change``.

    Returns the (unchanged) input prompt as the "modified" prompt so the saved
    ``.prompt`` content is deterministic. The point of the E2E is the gate that
    runs *after* the save, not the model's edit.
    """
    return input_prompt_content, 0.0, _FAKE_MODEL


def _fake_construct_paths(
    *,
    input_file_paths,
    force,
    quiet,
    command,
    command_options,
    context_override=None,
):
    """Read the real fixture files; leave output path to the explicit --output."""
    input_strings = {
        key: Path(value).read_text(encoding="utf-8")
        for key, value in input_file_paths.items()
    }
    resolved_config: dict = {}
    output_file_paths: dict = {}
    language = "python"
    return resolved_config, input_strings, output_file_paths, language


def _fake_resolve_effective_config(ctx, resolved_config):
    """Deterministic generation knobs (no CLI/pddrc precedence needed for E2E)."""
    return {"strength": 0.5, "temperature": 0.0, "time": 0.25}


def _fake_run_agentic_architecture(*args, **kwargs):
    """Stand in for the model-backed prompt writer in ``pdd generate``.

    Writes the configured prompt text to ``PDD_E2E_GEN_PROMPT_PATH`` (exactly as
    the real orchestrator would emit a ``.prompt`` file) and returns its path so
    the real gate runs against a real on-disk prompt.
    """
    target = Path(os.environ["PDD_E2E_GEN_PROMPT_PATH"]).resolve()
    text = Path(os.environ["PDD_E2E_PROMPT_TEXT_FILE"]).read_text(encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return True, "ok (e2e stub)", 0.0, _FAKE_MODEL, [str(target)]


def main() -> None:
    cli_args = sys.argv[1:]
    with ExitStack() as stack:
        stack.enter_context(patch("pdd.change_main.change_func", _fake_change_func))
        stack.enter_context(
            patch("pdd.change_main.construct_paths", _fake_construct_paths)
        )
        stack.enter_context(
            patch(
                "pdd.change_main.resolve_effective_config",
                _fake_resolve_effective_config,
            )
        )
        stack.enter_context(
            patch(
                "pdd.agentic_architecture.run_agentic_architecture",
                _fake_run_agentic_architecture,
            )
        )
        # Import and run the real CLI while the provider stubs are active. Click's
        # standalone mode converts the gate's ``Exit(code)`` into ``sys.exit(code)``
        # so the parent process observes a genuine exit status.
        from pdd.cli import cli  # noqa: WPS433 (import inside the stubbed context)

        cli.main(args=cli_args, prog_name="pdd", standalone_mode=True)


if __name__ == "__main__":
    main()
