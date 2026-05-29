import os
import subprocess
import json
from pathlib import Path
import pytest
from click.testing import CliRunner
from pdd.cli import cli
from pdd.user_story_tests import _render_story_markdown_from_prompts

def test_e2e_architecture_sync_stable():
    """Verify pdd sync-architecture --dry-run confirms architecture is in sync."""
    result = subprocess.run(
        ["python3", "-m", "pdd.cli", "sync-architecture", "--dry-run"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Dry run: would update 0 module(s)" in result.stdout
    
    # Verify no prefix error for evidence_manifest in architecture.json
    with open("architecture.json", "r") as f:
        arch_content = f.read()
    assert "evidence_manifest_python.prompt" in arch_content
    assert "pdd/evidence_manifest_python.prompt" not in arch_content

def test_e2e_user_story_generation_seeding(tmp_path):
    """Verify that user story generation seeds ## Covers from prompt contracts."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # Create a prompt with contracts
    prompt_content = """
# Test Prompt
<contract_rules>
R1: Verify that A does B.
R2: Verify that C does D.
</contract_rules>
"""
    prompt_path = prompts_dir / "test_python.prompt"
    prompt_path.write_text(prompt_content)
    
    # We need to make sure the imports inside pdd.user_story_tests work.
    # Since we are running in the project root, it should be fine.
    
    markdown = _render_story_markdown_from_prompts(
        title="Test Story",
        prompt_paths=[prompt_path],
        prompts_root=prompts_dir
    )
    
    assert "## Covers" in markdown
    assert "test_python.prompt#R1: R1: Verify that A does B." in markdown
    assert "test_python.prompt#R2: R2: Verify that C does D." in markdown
    assert "## Oracle" in markdown
    assert "## Non-Oracle" in markdown
    assert "## Negative Cases" in markdown
    assert "## Acceptance Criteria" in markdown

def test_e2e_change_command_help():
    """Verify pdd change --help works without import errors (verifies lazy imports)."""
    runner = CliRunner()
    result = runner.invoke(cli, ["change", "--help"])
    assert result.exit_code == 0
    assert "Modify an input prompt file" in result.output

def test_e2e_checkup_command_help():
    """Verify pdd checkup --help works (verifies integration doesn't break CLI)."""
    runner = CliRunner()
    result = runner.invoke(cli, ["checkup", "--help"])
    assert result.exit_code == 0
    assert "Run agentic health checkup" in result.output

def test_e2e_user_story_flow_integration(tmp_path):
    """Test the integration between user story tests and the rest of the system."""
    prompts_dir = tmp_path / "prompts"
    stories_dir = tmp_path / "user_stories"
    prompts_dir.mkdir()
    stories_dir.mkdir()
    
    prompt_path = prompts_dir / "auth_python.prompt"
    prompt_path.write_text("Handle authentication.", encoding="utf-8")
    
    from pdd.user_story_tests import generate_user_story
    
    # Mocking detect_change to avoid actual LLM calls
    from unittest.mock import patch
    with patch("pdd.user_story_tests.detect_change") as mock_detect:
        mock_detect.return_value = ([], 0.1, "mock-model")
        success, message, cost, model, story_file, linked_prompts = generate_user_story(
            prompt_files=[str(prompt_path)],
            stories_dir=str(stories_dir),
            prompts_dir=str(prompts_dir),
        )
        
    assert success is True
    assert Path(story_file).exists()
    content = Path(story_file).read_text()
    assert "## Story" in content
    assert "## Prompt Scope" in content
    assert "## Covers" in content
    assert "auth_python.prompt" in content
