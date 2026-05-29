import os
from unittest.mock import MagicMock, patch
import pytest
import click
from pdd.server.click_executor import ClickCommandExecutor, CapturedOutput, get_pdd_command
from pdd.core.cloud import CloudConfig, CLOUD_ENDPOINTS

def test_cloud_config_endpoints_integration():
    """
    Test that the new submitCommand endpoint is correctly registered and resolvable.
    """
    assert "submitCommand" in CLOUD_ENDPOINTS
    url = CloudConfig.get_endpoint_url("submitCommand")
    assert "/submitCommand" in url
    
    # Test fallback for unknown endpoint
    url = CloudConfig.get_endpoint_url("unknownEndpoint")
    assert "/unknownEndpoint" in url

def test_click_command_executor_basic():
    """
    Test that ClickCommandExecutor can execute a command and capture output.
    """
    executor = ClickCommandExecutor()
    
    @click.command("test-cmd")
    @click.option("--name", default="World")
    def test_cmd(name):
        click.echo(f"Hello, {name}!")
        
    result = executor.execute(test_cmd, options={"name": "PDD"})
    
    assert result.exit_code == 0
    assert "Hello, PDD!" in result.stdout
    assert isinstance(result, CapturedOutput)

def test_click_command_executor_with_list_type_hint():
    """
    Test that the executor correctly handles commands that might use List type hints,
    verifying the fix for the NameError.
    """
    from typing import List
    
    executor = ClickCommandExecutor()
    
    @click.command("test-list")
    @click.argument("items", nargs=-1)
    def test_list_cmd(items: List[str]):
        for item in items:
            click.echo(f"Item: {item}")
            
    result = executor.execute(test_list_cmd, args={"items": ["a", "b", "c"]})
    
    assert result.exit_code == 0
    assert "Item: a" in result.stdout
    assert "Item: b" in result.stdout
    assert "Item: c" in result.stdout

def test_get_pdd_command_integration():
    """
    Test that get_pdd_command correctly retrieves registered commands.
    """
    # Test with a known command
    cmd = get_pdd_command("sync")
    assert cmd is not None
    assert cmd.name == "sync"
    
    # Test with unknown command
    cmd = get_pdd_command("non-existent")
    assert cmd is None
