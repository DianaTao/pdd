import os
import sys
from unittest.mock import patch
import click
from click.testing import CliRunner
from pdd.core.cli import cli as cli_command

@patch('pdd.core.cli.auto_update')
def test_repro(mock_auto_update):
    runner = CliRunner()
    
    @cli_command.command()
    def dummy():
        click.echo("dummy called")
    
    print(f"DEBUG: PDD_AUTO_UPDATE={os.getenv('PDD_AUTO_UPDATE')}")
    result = runner.invoke(cli_command, ["dummy"])
    print(f"DEBUG: exit_code={result.exit_code}")
    print(f"DEBUG: output={result.output}")
    print(f"DEBUG: mock_auto_update.called={mock_auto_update.called}")
    if not mock_auto_update.called:
        print("FAIL: auto_update was NOT called")
    else:
        print("SUCCESS: auto_update was called")

if __name__ == "__main__":
    test_repro()
