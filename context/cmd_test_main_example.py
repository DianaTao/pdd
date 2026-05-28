from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Ensure the parent directory is in sys.path so pdd can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import click
from rich.console import Console

# Import the main entry point we want to demonstrate
from pdd.cmd_test_main import cmd_test_main

console = Console()

def run_example() -> None:
    """
    Demonstrates how to use the 'cmd_test_main' function to generate and augment unit tests.
    
    This example covers:
    1. Single-LLM unit test generation (legacy/standard flow).
    2. Increasing coverage using a coverage report (legacy/standard flow).
    3. Agentic unit test generation (advanced multi-turn pipeline).
    
    All external file operations, config resolution, and LLM calls are mocked to ensure 
    this example runs standalone and completes instantly without external network requests.
    
    Parameters shown in this example:
    - `ctx` (click.Context): The Click context containing global flags.
    - `prompt_file` (str): Path to the prompt file.
    - `code_file` (str): Path to the code file.
    - `output` (str | None): Target path for the test code.
    - `language` (str | None): Specific programming language.
    - `coverage_report` (str | None): Path to an optional coverage report file.
    - `existing_tests` (list[str] | None): Paths to existing test files.
    - `target_coverage` (float | None): Target coverage percentage.
    - `merge` (bool): Whether to append generated tests to existing tests.
    - `strength` (float | None): LLM strength parameter (0.0 to 1.0).
    - `temperature` (float | None): LLM temperature parameter (0.0 to 1.0).
    - `manual` (bool): Force legacy generation.
    
    Outputs returned:
    - `generated_code` (str): The generated unit test code.
    - `total_cost` (float): Cost of the LLM API calls in USD.
    - `model_name` (str): The model used for generation.
    - `agentic_success` (bool | None): True/False for agentic non-Python generation, None for Python.
    - `error_message` (str): Diagnostics or error message (empty string on success).
    """
    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print("[bold cyan]       PDD cmd_test_main API Demonstration        [/bold cyan]")
    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print()

    # Create dummy files for paths so that construct_paths doesn't fail if it accesses files
    # However, since we mock construct_paths, we don't strictly need them, but keeping them keeps it realistic
    prompt_path = "math_ops.prompt"
    code_path = "math_ops.py"
    output_path = "test_math_ops.py"
    
    # ---------------------------------------------------------------------------
    # Case 1: Standard Unit Test Generation (Python)
    # ---------------------------------------------------------------------------
    console.print("[bold green]--- Case 1: Standard Unit Test Generation ---[/bold green]")
    
    # Mocking construct_paths and resolve_effective_config
    mock_resolved_config = {"strength": 0.3, "temperature": 0.1, "time": 0.2}
    mock_input_strings = {
        "prompt_file": "Write tests for addition and subtraction",
        "code_file": "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b"
    }
    mock_output_paths = {"output_file": output_path}
    
    ctx = click.Context(click.Command("test"))
    ctx.obj = {
        "verbose": False,
        "force": True,
        "quiet": True,
        "local": True,
        "context": None,
        "confirm_callback": None,
        "agentic_mode": False
    }

    mock_test_code = """import pytest
from math_ops import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2
"""

    with patch("pdd.cmd_test_main.construct_paths") as mock_paths, \
         patch("pdd.cmd_test_main.resolve_effective_config") as mock_eff_config, \
         patch("pdd.cmd_test_main.generate_test") as mock_gen_test, \
         patch("builtins.open", mock_open()) as mock_file_open:
         
        mock_paths.return_value = (mock_resolved_config, mock_input_strings, mock_output_paths, "python")
        mock_eff_config.return_value = {"strength": 0.3, "temperature": 0.1, "time": 0.2}
        mock_gen_test.return_value = (mock_test_code, 0.0015, "gpt-4-mock")
        
        test_code, cost, model, success, err = cmd_test_main(
            ctx=ctx,
            prompt_file=prompt_path,
            code_file=code_path,
            output=output_path,
            language="python",
            strength=0.3,
            temperature=0.1
        )
        
        console.print(f"Generated test code ({len(test_code)} chars).")
        console.print(f"Model: {model}")
        console.print(f"Cost: ${cost:.6f} USD")
        console.print(f"Agentic Success: {success}")
        console.print(f"Error Message: '{err}'")
        console.print()

    # ---------------------------------------------------------------------------
    # Case 2: Coverage Augmentation (Standard/Legacy Mode)
    # ---------------------------------------------------------------------------
    console.print("[bold green]--- Case 2: Coverage Augmentation ---[/bold green]")
    
    mock_coverage_report = "Name          Stmts   Miss  Cover\n---------------------------------\nmath_ops.py       6      2    67%"
    
    with patch("pdd.cmd_test_main.construct_paths") as mock_paths, \
         patch("pdd.cmd_test_main.resolve_effective_config") as mock_eff_config, \
         patch("pdd.cmd_test_main.increase_tests") as mock_inc_tests, \
         patch("pathlib.Path.read_text") as mock_read_text, \
         patch("builtins.open", mock_open()) as mock_file_open:
         
        mock_paths.return_value = (mock_resolved_config, mock_input_strings, mock_output_paths, "python")
        mock_eff_config.return_value = {"strength": 0.3, "temperature": 0.1, "time": 0.2}
        mock_read_text.return_value = "def test_add(): pass"
        mock_inc_tests.return_value = (mock_test_code, 0.0025, "gpt-4-mock")
        
        test_code, cost, model, success, err = cmd_test_main(
            ctx=ctx,
            prompt_file=prompt_path,
            code_file=code_path,
            output=output_path,
            language="python",
            coverage_report="math_ops_coverage.txt",
            existing_tests=["test_math_ops_existing.py"],
            strength=0.3,
            temperature=0.1
        )
        
        console.print(f"Augmented test code ({len(test_code)} chars).")
        console.print(f"Model: {model}")
        console.print(f"Cost: ${cost:.6f} USD")
        console.print(f"Agentic Success: {success}")
        console.print(f"Error Message: '{err}'")
        console.print()

    # ---------------------------------------------------------------------------
    # Case 3: Agentic Test Generation
    # ---------------------------------------------------------------------------
    console.print("[bold green]--- Case 3: Agentic Test Generation ---[/bold green]")
    
    # Toggle agentic mode in Click Context
    ctx.obj["agentic_mode"] = True
    
    with patch("pdd.cmd_test_main.construct_paths") as mock_paths, \
         patch("pdd.cmd_test_main.resolve_effective_config") as mock_eff_config, \
         patch("pdd.cmd_test_main.run_agentic_test_generate") as mock_agentic_gen:
         
        mock_paths.return_value = (mock_resolved_config, mock_input_strings, mock_output_paths, "typescript")
        mock_eff_config.return_value = {"strength": 0.5, "temperature": 0.0, "time": 0.5}
        
        # Simulating a successful agentic run
        mock_agentic_gen.return_value = (
            "describe('math_ops', () => { ... })",
            0.0450,
            "claude-3-5-sonnet",
            True,
            ""
        )
        
        test_code, cost, model, success, err = cmd_test_main(
            ctx=ctx,
            prompt_file="math_ops.prompt",
            code_file="math_ops.ts",
            output="math_ops.test.ts",
            language="typescript"
        )
        
        console.print(f"Agentic generated test code ({len(test_code)} chars).")
        console.print(f"Model: {model}")
        console.print(f"Cost: ${cost:.6f} USD")
        console.print(f"Agentic Success: {success}")
        console.print(f"Error Message: '{err}'")
        console.print()
        
    console.print("[bold cyan]==================================================[/bold cyan]")
    console.print("[bold cyan]             Demonstration Complete              [/bold cyan]")
    console.print("[bold cyan]==================================================[/bold cyan]")

if __name__ == "__main__":
    run_example()
