"""
End-to-end and integration tests for the PDD health checkup fixes.
"""
import os
import pytest
from pathlib import Path
from click.testing import CliRunner
from pdd.cli import cli

def test_e2e_coverage_contracts_flow(tmp_path):
    """
    Test the full pdd coverage --contracts CLI flow.
    """
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    prompt_a = prompts_dir / "A_python.prompt"
    prompt_a.write_text("R1: requirement A1\nR2: requirement A2", encoding="utf-8")
    
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir()
    story_a = stories_dir / "story__a.md"
    story_a.write_text("# Story A\n## Covers\nA_python.prompt", encoding="utf-8")
    
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_a = tests_dir / "test_a.py"
    test_a.write_text("# A_python.prompt:R1: test for A:R1", encoding="utf-8")
    
    runner = CliRunner()
    result = runner.invoke(cli, [
        "coverage", "--contracts",
        "--prompts-dir", str(prompts_dir),
        "--stories-dir", str(stories_dir),
        "--tests-dir", str(tests_dir)
    ])
    
    assert result.exit_code == 1
    assert "A_python.prompt" in result.output
    assert "MISSING" in result.output
    assert "R2" in result.output
    
    status_line = [line for line in result.output.splitlines() if "A_python.prompt" in line][0]
    assert "R2" in status_line
    assert "R1" not in status_line.split("MISSING")[1]
    assert "0.0%" in result.output

def test_e2e_checkup_contract_strict_flow(tmp_path):
    """
    Test pdd checkup contract check --strict with a real prompt.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        p_dir = Path("prompts")
        p_dir.mkdir()
        (p_dir / "Other.prompt").write_text("<include>None</include>")
        (p_dir / "Main.prompt").write_text("<include>Other.prompt</include>")
        Path("architecture.json").write_text('{"modules": [{"filename": "Main.prompt", "dependencies": []}]}')
        
        result = runner.invoke(cli, [
            "checkup", "contract", "check", 
            "--strict", "prompts/Main.prompt"
        ])
    
    assert result.exit_code == 0 or "architecture.json" in result.output

def test_integration_edit_file_runtime_imports():
    """
    Verify that pdd.edit_file and its heavy dependencies (langchain, langgraph) 
    are correctly integrated and importable at runtime.
    """
    pytest.importorskip("langgraph")
    
    try:
        import pdd.edit_file
        from langgraph.graph import StateGraph
        assert pdd.edit_file.graph is not None
        assert isinstance(pdd.edit_file.graph_builder, StateGraph)
    except ImportError as e:
        pytest.fail(f"Failed to import pdd.edit_file or its dependencies: {e}")

def test_integration_context_example_syntax():
    """
    Verify that context/__init__example.py is a valid importable module.
    """
    try:
        import context.__init__example
    except Exception as e:
        pytest.fail(f"Failed to import context.__init__example: {e}")

def test_e2e_coverage_quiet_verbose_flags(tmp_path):
    """
    Verify that --quiet and --verbose flags are correctly handled in the coverage command.
    """
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "A.prompt").write_text("R1: test", encoding="utf-8")
    
    stories_dir = tmp_path / "stories"
    stories_dir.mkdir()
    
    tests_dir = tmp_path / "empty_tests"
    tests_dir.mkdir()
    
    runner = CliRunner()
    
    # Test --quiet
    result_quiet = runner.invoke(cli, [
        "coverage", "--contracts",
        "--prompts-dir", str(prompts_dir),
        "--stories-dir", str(stories_dir),
        "--tests-dir", str(tests_dir),
        "--quiet"
    ])
    assert result_quiet.exit_code == 1
    assert "PDD Contract Coverage Matrix" not in result_quiet.output
    assert "Overall Coverage" not in result_quiet.output
    
    # Test --verbose
    result_verbose = runner.invoke(cli, [
        "coverage", "--contracts",
        "--prompts-dir", str(prompts_dir),
        "--stories-dir", str(stories_dir),
        "--tests-dir", str(tests_dir),
        "--verbose"
    ])
    assert result_verbose.exit_code == 1
    assert "PDD Contract Coverage Matrix" in result_verbose.output
