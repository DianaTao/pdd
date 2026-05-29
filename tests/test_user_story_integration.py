
import pytest
import os
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from pathlib import Path
from pdd.cli import cli

def test_pdd_detect_stories_cli_integration(tmp_path):
    """Test 'pdd detect --stories' integration with run_user_story_tests."""
    runner = CliRunner()
    
    # We need to mock run_user_story_tests in pdd.commands.analysis
    with patch("pdd.commands.analysis.run_user_story_tests") as mock_run:
        mock_run.return_value = (True, [], 0.1, "mock-model")
        
        # We use a dummy prompts-dir and stories-dir to avoid scanning the whole repo
        prompts_dir = tmp_path / "prompts"
        stories_dir = tmp_path / "user_stories"
        prompts_dir.mkdir()
        stories_dir.mkdir()
        
        result = runner.invoke(cli, [
            "detect", "--stories", 
            "--stories-dir", str(stories_dir),
            "--prompts-dir", str(prompts_dir)
        ])
        
        assert result.exit_code == 0
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["stories_dir"] == str(stories_dir)
        assert kwargs["prompts_dir"] == str(prompts_dir)

def test_pdd_fix_story_cli_integration(tmp_path):
    """Test 'pdd fix story__*.md' integration with run_user_story_fix."""
    runner = CliRunner()
    
    story_file = tmp_path / "story__test.md"
    story_file.write_text("As a user...")
    
    # Patch it in pdd.user_story_tests since it's imported locally in pdd.commands.fix
    with patch("pdd.user_story_tests.run_user_story_fix") as mock_run:
        mock_run.return_value = (True, "Fixed", 0.5, "mock-model", ["fixed.prompt"])
        
        result = runner.invoke(cli, ["fix", str(story_file)])
        
        assert result.exit_code == 0
        mock_run.assert_called_once()
        # Verify it was called with story_file
        _, kwargs = mock_run.call_args
        assert kwargs.get("story_file") == str(story_file)

def test_pdd_test_story_generation_integration(tmp_path):
    """Test 'pdd test prompt.prompt' integration with generate_user_story."""
    runner = CliRunner()
    
    prompt_file = tmp_path / "test.prompt"
    prompt_file.write_text("prompt content")
    
    # Patch it in pdd.commands.generate where it's used
    with patch("pdd.commands.generate.generate_user_story") as mock_gen:
        mock_gen.return_value = (True, "Generated", 0.5, "mock-model", "story__test.md", ["test.prompt"])
        
        result = runner.invoke(cli, ["test", str(prompt_file)])
        
        assert result.exit_code == 0
        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        # The prompt file is passed in the prompt_files argument
        assert any(str(prompt_file) in p for p in kwargs["prompt_files"])

def test_user_story_tests_contract_integration(tmp_path):
    """Test interaction between user_story_tests and contract_ir for seeding Covers."""
    from pdd.user_story_tests import _render_story_markdown_from_prompts
    
    prompt_file = tmp_path / "test_python.prompt"
    # Create a prompt with a valid contract section
    # Based on extract_sections, it looks for <contract_rules>
    prompt_file.write_text("""
<pdd-interface>
  <contract_rules>
R1: Behavior 1
R2: Behavior 2
  </contract_rules>
</pdd-interface>
""")
    
    markdown = _render_story_markdown_from_prompts(
        title="Integration Story",
        prompt_paths=[prompt_file],
        prompts_root=tmp_path
    )
    
    # Verify that the rules were extracted and formatted in the Covers section
    assert "## Covers" in markdown
    assert "test_python.prompt#R1" in markdown
    assert "test_python.prompt#R2" in markdown

def test_ci_drift_heal_dependency_integration():
    """Verify that ci_drift_heal recognizes user_story_tests in its dependency context."""
    import inspect
    import pdd.ci_drift_heal
    
    # The import is inside _discover_modules function
    if hasattr(pdd.ci_drift_heal, '_discover_modules'):
        source = inspect.getsource(pdd.ci_drift_heal._discover_modules)
        assert "from pdd.user_story_tests import discover_prompt_files" in source
    else:
        # Fallback to checking the file content
        content = Path(pdd.ci_drift_heal.__file__).read_text()
        assert "from pdd.user_story_tests import discover_prompt_files" in content
