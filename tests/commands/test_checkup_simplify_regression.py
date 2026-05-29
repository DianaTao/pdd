import pytest
from click.testing import CliRunner
from pdd.commands.checkup_simplify import checkup_simplify
from pdd.commands.checkup import checkup
from unittest.mock import MagicMock, patch

def test_checkup_simplify_return_type_regression():
    """Verify checkup_simplify returns the expected 3-tuple."""
    # We don't need to run the full command, just verify the function signature and return behavior
    # by mocking the underlying run_checkup_simplify call.
    with patch("pdd.commands.checkup_simplify.run_checkup_simplify") as mock_run:
        mock_result = MagicMock()
        mock_result.provider = "claude"
        mock_result.cost = 0.05
        mock_result.evidence_path = "/tmp/evidence.json"
        mock_result.summary_lines = ["line1"]
        mock_result.exit_code = 0
        mock_run.return_value = mock_result
        
        runner = CliRunner()
        # Use standalone_mode=False to get the return value
        result = runner.invoke(checkup_simplify, ["."], standalone_mode=False)
        
        assert isinstance(result.return_value, tuple)
        assert len(result.return_value) == 3
        assert result.return_value == ("claude", 0.05, "/tmp/evidence.json")

def test_checkup_dispatch_to_simplify_regression():
    """Verify pdd checkup simplify correctly handles the return tuple."""
    with patch("pdd.commands.checkup_simplify.checkup_simplify.main") as mock_simplify_main:
        mock_simplify_main.return_value = ("claude", 0.05, "/tmp/evidence.json")
        
        runner = CliRunner()
        # Calling 'pdd checkup simplify'
        result = runner.invoke(checkup, ["simplify"], standalone_mode=False)
        
        # If the fix was reverted, checkup would fail when trying to handle the return value
        # or would not return it correctly.
        assert result.return_value == ("claude", 0.05, "/tmp/evidence.json")
