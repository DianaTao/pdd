from typing import List
import click
import pytest
from pdd.server.click_executor import _get_command_positional_args

def test_get_command_positional_args_regression():
    """Verify that _get_command_positional_args works and doesn't raise NameError for List."""
    @click.command()
    @click.argument("arg1")
    @click.argument("arg2")
    def my_command(arg1, arg2):
        pass
    
    pos_args = _get_command_positional_args(my_command)
    assert pos_args == ["arg1", "arg2"]
    assert isinstance(pos_args, list)
