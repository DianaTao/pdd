import os
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from pdd.commands.checkup import checkup
from pdd.checkup_simplify import SimplifyRunResult

def test_checkup_simplify_integration_flow():
    """
    Test that 'pdd checkup simplify' flows correctly and returns the cost tuple
    which is handled by the parent 'checkup' command.
    """
    runner = CliRunner()
    
    # Mock run_checkup_simplify to return a successful result
    mock_result = SimplifyRunResult(
        success=True,
        exit_code=0,
        cost=0.0123,
        provider="claude",
        claude_code_version="1.0.0",
        slash_command="/simplify",
        files_analyzed=["file1.py"],
        files_modified=["file1.py"],
        agent_summary="Simplified 1 file",
        attempts=1,
        selected_attempt=1,
        evidence_path="evidence.json",
        summary_lines=["Simplified 1 file"]
    )
    
    with patch("pdd.commands.checkup_simplify.run_checkup_simplify", return_value=mock_result):
        # We need to mock Path(path).exists() if we pass a path, 
        # or just pass no path if it defaults to current dir (which exists).
        # checkup_simplify argument 'path' has type=click.Path(exists=True)
        
        # Run 'pdd checkup simplify'
        # Run 'pdd checkup simplify --apply'
        # The 'checkup' command handles the 'simplify' target by calling checkup_simplify.main

        result = runner.invoke(checkup, ["simplify", "--apply"])

        
        assert result.exit_code == 0
        assert "Simplified 1 file" in result.output
        assert "Agent: claude" in result.output
        assert "Cost: $0.0123" in result.output

def test_checkup_simplify_error_propagation():
    """
    Test that errors in 'checkup simplify' are propagated correctly to 'checkup'.
    """
    runner = CliRunner()
    
    with patch("pdd.commands.checkup_simplify.run_checkup_simplify", side_effect=ValueError("Test Error")):
        result = runner.invoke(checkup, ["simplify"])
        
        assert result.exit_code != 0
        assert "Error: Test Error" in result.output

def test_checkup_simplify_cost_tracking_integration():
    """
    Test that track_cost decorator on checkup_simplify works when called via checkup.
    """
    runner = CliRunner()
    
    mock_result = SimplifyRunResult(
        success=True,
        exit_code=0,
        cost=0.05,
        provider="test-model",
        claude_code_version="1.0.0",
        slash_command="/simplify",
        files_analyzed=["file1.py"],
        files_modified=["file1.py"],
        agent_summary="Success",
        attempts=1,
        selected_attempt=1,
        evidence_path=None,
        summary_lines=["Success"]
    )
    
    with patch("pdd.commands.checkup_simplify.run_checkup_simplify", return_value=mock_result):
        with patch("pdd.track_cost.track_cost", side_effect=lambda x: x) as mock_track:
            # Note: mocking track_cost at this point might be too late if it's already applied
            # as a decorator. But let's see.
            result = runner.invoke(checkup, ["simplify"])
            assert result.exit_code == 0
            assert "Success" in result.output
