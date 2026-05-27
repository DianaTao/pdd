"""
Regression tests for Issue #823.
"""
import os
from pathlib import Path
import pytest
from click.testing import CliRunner
from pdd.cli import cli
from pdd.coverage_contracts import _story_links_prompt

def test_story_links_prompt_with_metadata():
    story_content = """# Title
<!-- pdd-story-prompts: foo_python.prompt, bar_python.prompt -->
## Story
..."""
    assert _story_links_prompt(story_content, "foo_python.prompt") is True
    assert _story_links_prompt(story_content, "bar_python.prompt") is True
    assert _story_links_prompt(story_content, "baz_python.prompt") is False

def test_story_links_prompt_with_covers_section():
    story_content = """# Title
## Story
...
## Covers
- foo_python.prompt
- bar_python.prompt
## Notes
..."""
    assert _story_links_prompt(story_content, "foo_python.prompt") is True
    assert _story_links_prompt(story_content, "bar_python.prompt") is True
    assert _story_links_prompt(story_content, "baz_python.prompt") is False

def test_coverage_contracts_cli_smoke():
    runner = CliRunner()
    # Mocking environment might be hard, so just check if command exists
    result = runner.invoke(cli, ["coverage", "--help"])
    assert result.exit_code == 0
    assert "Cross-reference module prompts against user stories" in result.output

def test_checkup_contract_check_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["checkup", "contract", "check", "--help"])
    assert result.exit_code == 0
    assert "Validate module interface contract" in result.output
    assert "--strict" in result.output
