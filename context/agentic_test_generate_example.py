from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch
from rich.console import Console

# Ensure the 'pdd' package can be imported regardless of working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdd.agentic_test_generate import run_agentic_test_generate

console = Console()


def mock_agent_behavior(instruction: str, cwd: Path, **kwargs: Any) -> tuple[bool, str, float, str]:
    """
    Simulates the behavior of an agentic CLI tool.
    
    It writes the mock test file directly to the workspace and returns a JSON response.
    """
    console.print("[Mock Agent] Executing single-pass test generation...")
    
    # The expected output test path is test_calculator.py inside the temporary directory.
    # In run_agentic_test_generate, the agent writes the test file directly.
    test_path = cwd / "test_calculator.py"
    test_content = (
        "from calculator import add\n\n"
        "def test_add() -> None:\n"
        "    assert add(2, 3) == 5\n"
    )
    test_path.write_text(test_content, encoding="utf-8")
    
    # Update modification time to ensure change detection works correctly
    os.utime(test_path, None)
    
    # Prepare the agent JSON response metadata
    response_json = (
        "{\n"
        '  "success": true,\n'
        '  "message": "Generated tests and validated that they pass."\n'
        "}"
    )
    
    # Returns (success, output, cost, provider)
    return True, response_json, 0.045, "mock-provider"


def run_example() -> None:
    """
    Demonstrates run_agentic_test_generate by setting up a temporary environment,
    mocking the agentic framework dependencies, and calling the function.
    
    Inputs:
    - None (set up dynamically in a temporary directory)
    
    Outputs:
    - None (prints status and results)
    """
    console.print("[bold blue]Agentic Test Generation Example[/bold blue]")
    console.print()

    with TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        
        # 1. Prepare files required by the module
        prompt_file = temp_dir / "calculator_prompt.md"
        prompt_file.write_text(
            "# Calculator Specification\n"
            "Create a module with a function `add(a, b)` that returns their sum.\n",
            encoding="utf-8"
        )
        
        code_file = temp_dir / "calculator.py"
        code_file.write_text(
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n",
            encoding="utf-8"
        )
        
        output_test_file = temp_dir / "test_calculator.py"

        # Mocking the load_prompt_template to return a dummy template string 
        # and run_agentic_task to simulate agent execution.
        dummy_template = (
            "Prompt Path: {prompt_path}\n"
            "Code Path: {code_path}\n"
            "Test Path: {test_path}\n"
            "Project Root: {project_root}\n"
            "Prompt Content: {prompt_content}\n"
            "Code Content: {code_content}\n"
        )

        with patch("pdd.agentic_test_generate.load_prompt_template", return_value=dummy_template), \
             patch("pdd.agentic_test_generate.run_agentic_task", side_effect=mock_agent_behavior):
            
            console.print("Calling run_agentic_test_generate...")
            
            generated_content, cost, model_name, success, error_message = run_agentic_test_generate(
                prompt_file=prompt_file,
                code_file=code_file,
                output_test_file=output_test_file,
                verbose=True,
                quiet=False
            )

        console.print()
        console.print("[bold green]Execution Results:[/bold green]")
        console.print(f"Success         : {success}")
        console.print(f"Model Name      : {model_name}")
        console.print(f"Estimated Cost  : ${cost:.4f}")
        console.print(f"Error Message   : {error_message}")
        console.print()
        console.print("[bold green]Generated Content:[/bold green]")
        console.print(generated_content)


if __name__ == "__main__":
    run_example()
