"""
Regression tests for coverage and story scoping fixes.
"""
import os
import pytest
from pathlib import Path
from click.testing import CliRunner
from pdd.cli import cli
from pdd.coverage_contracts import scan_test_evidence, build_coverage

def test_coverage_false_positives(tmp_path):
    """
    Test that one test_R1_* does not mark both prompts as covered 
    if they both define R1.
    """
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    
    # Prompt A defines R1
    prompt_a = prompts_dir / "A_python.prompt"
    prompt_a.write_text("R1: requirement A", encoding="utf-8")
    
    # Prompt B defines R1
    prompt_b = prompts_dir / "B_python.prompt"
    prompt_b.write_text("R1: requirement B", encoding="utf-8")
    
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    
    # Test A covers A:R1
    test_a = tests_dir / "test_A.py"
    test_a.write_text("# R1: test for A", encoding="utf-8")
    
    evidence = scan_test_evidence(tests_dir)
    coverage = build_coverage([prompt_a, prompt_b], [], evidence)
    
    # Prompt A should be covered for R1
    assert "A_python.prompt" in coverage
    assert coverage["A_python.prompt"]["missing_reqs"] == []
    assert "test_A.py" in str(coverage["A_python.prompt"]["tests"])
    
    # Prompt B should NOT be covered for R1
    assert "B_python.prompt" in coverage
    assert coverage["B_python.prompt"]["missing_reqs"] == ["R1"]
    assert coverage["B_python.prompt"]["tests"] == []

def test_metadata_less_story_scoping(tmp_path):
    """
    Test that a story with no metadata or ## Covers section is handled consistently.
    """
    from pdd.user_story_tests import run_user_story_tests
    
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_a = prompts_dir / "A_python.prompt"
    prompt_a.write_text("R1: requirement A", encoding="utf-8")
    
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir()
    
    # Story with NO links
    story_path = stories_dir / "story__no_links.md"
    story_path.write_text("# My Story\nNo links here.", encoding="utf-8")
    
    # Story with ## Covers
    story_covers = stories_dir / "story__covers.md"
    story_covers.write_text("# My Story\n## Covers\nA_python.prompt", encoding="utf-8")
    
    # run_user_story_tests should skip story_path but run story_covers
    # We mock detect_change to see what's called
    import pdd.user_story_tests
    from unittest.mock import patch
    
    with patch("pdd.user_story_tests.detect_change") as mock_detect:
        mock_detect.return_value = ([], 0.0, "mock-model")
        
        success, results, cost, model = run_user_story_tests(
            prompts_dir=str(prompts_dir),
            stories_dir=str(stories_dir),
            quiet=True
        )
        
        # Should only have one result (for story_covers)
        assert len(results) == 1
        assert results[0]["story"] == str(story_covers)
        
        # mock_detect should have been called once with prompt_a
        assert mock_detect.call_count == 1
        call_args = mock_detect.call_args[0]
        assert str(prompt_a) in call_args[0]

def test_checkup_contract_strict_delegation():
    """
    Test that --strict flag is correctly passed to contract check 
    and not consumed by checkup.
    """
    runner = CliRunner()
    # We use a non-existent prompt to see if it reaches the validation logic
    result = runner.invoke(cli, ["checkup", "contract", "check", "--strict", "nonexistent.prompt"])
    
    # It should not fail with "No such option: --strict"
    assert "No such option: --strict" not in result.output
    # It might fail because prompt doesn't exist, which is fine
    # But it should show the validation error or the help
    assert result.exit_code != 0 or "Validate module interface contract" in result.output
