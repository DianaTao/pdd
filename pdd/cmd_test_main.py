from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Any

import click
from rich.console import Console

from .construct_paths import construct_paths
from .generate_test import generate_test
from .increase_tests import increase_tests
from .config_resolution import resolve_effective_config
from .core.cloud import CloudConfig
from .agentic_test_generate import run_agentic_test_generate

console = Console()

def cmd_test_main(
    ctx: click.Context,
    prompt_file: str,
    code_file: str,
    output: Optional[str] = None,
    language: Optional[str] = None,
    coverage_report: Optional[str] = None,
    existing_tests: Optional[List[str]] = None,
    target_coverage: Optional[float] = None,
    merge: bool = False,
    strength: Optional[float] = None,
    temperature: Optional[float] = None,
    manual: bool = False,
) -> Tuple[str, float, str, Optional[bool], str]:
    """
    CLI wrapper for generating or enhancing unit tests.
    """
    try:
        import requests
    except ImportError:
        requests = None

    try:
        # 1. Resolve basic context variables
        force = ctx.obj.get("force", False)
        quiet = ctx.obj.get("quiet", False)
        verbose = ctx.obj.get("verbose", False)
        context_override = ctx.obj.get("context")
        confirm_callback = ctx.obj.get("confirm_callback")
        is_local = ctx.obj.get("local", False)

        # 2. Build input/output paths
        input_file_paths = {
            "prompt_file": prompt_file,
            "code_file": code_file,
        }
        if coverage_report:
            input_file_paths["coverage_report"] = coverage_report
        if existing_tests and len(existing_tests) > 0:
            input_file_paths["existing_tests"] = existing_tests[0]

        command_options = {
            "output": output,
            "language": language,
            "merge": merge,
            "target_coverage": target_coverage,
        }

        resolved_config, input_strings, output_file_paths, detected_language = construct_paths(
            input_file_paths=input_file_paths,
            force=force,
            quiet=quiet,
            command="test",
            command_options=command_options,
            context_override=context_override,
            confirm_callback=confirm_callback
        )

        # 3. Resolve effective config
        param_overrides = {}
        if strength is not None:
            param_overrides["strength"] = strength
        if temperature is not None:
            param_overrides["temperature"] = temperature
        
        eff_config = resolve_effective_config(ctx, resolved_config, param_overrides=param_overrides)
        eff_strength = eff_config.get("strength")
        eff_temperature = eff_config.get("temperature")
        eff_time = eff_config.get("time")

        # 4. Handle existing tests concatenation
        existing_tests_content = None
        if existing_tests:
            contents = []
            for et in existing_tests:
                try:
                    contents.append(Path(et).read_text(encoding="utf-8"))
                except Exception as e:
                    return "", 0.0, "", None, f"Error reading existing test file {et}: {e}"
            existing_tests_content = "\n".join(contents)
            input_strings["existing_tests"] = existing_tests_content

        code_content = input_strings.get("code_file", "")
        prompt_content = input_strings.get("prompt_file", "")
        coverage_report_content = input_strings.get("coverage_report")

        # 5. Agentic generation detection
        use_agentic_tests = not manual and (
            (detected_language.lower() != 'python') or ctx.obj.get('agentic_mode', False)
        )

        output_file = output_file_paths.get("output_file")
        if not output_file:
            return "", 0.0, "", None, "Error: Could not resolve output path."

        if use_agentic_tests:
            if verbose:
                console.print("[bold cyan]Using agentic test generation pipeline...[/bold cyan]")
            generated_content, total_cost, model_name, agentic_success, error_message = run_agentic_test_generate(
                prompt_file=prompt_file,
                code_file=code_file,
                output_test_file=output_file,
                verbose=verbose,
                quiet=quiet,
            )
            return generated_content, total_cost, model_name, agentic_success, error_message

        # 6. Pre-validation for coverage report
        if coverage_report and not existing_tests:
            console.print("[bold red]Error: 'existing_tests' is required when providing a coverage report.[/bold red]")
            return "", 0.0, "", None, "Error: 'existing_tests' is required when providing a coverage report."

        source_file_path = str(Path(code_file).expanduser().resolve())
        test_file_path = str(Path(output_file).expanduser().resolve())
        module_name = Path(source_file_path).stem

        # Define local fallbacks
        def run_local_fallback() -> Tuple[str, float, str]:
            if coverage_report:
                return increase_tests(
                    existing_unit_tests=existing_tests_content or "",
                    coverage_report=coverage_report_content or "",
                    code=code_content,
                    prompt_that_generated_code=prompt_content,
                    language=detected_language,
                    strength=eff_strength,
                    temperature=eff_temperature,
                    time=eff_time,
                    verbose=verbose
                )
            else:
                is_example = Path(code_file).stem.endswith("_example")
                return generate_test(
                    prompt=prompt_content,
                    code=None if is_example else code_content,
                    example=code_content if is_example else None,
                    strength=eff_strength,
                    temperature=eff_temperature,
                    time=eff_time,
                    language=detected_language,
                    verbose=verbose,
                    source_file_path=source_file_path,
                    test_file_path=test_file_path,
                    module_name=module_name,
                    existing_tests=existing_tests_content
                )

        generated_test, total_cost, model_name = "", 0.0, ""

        if is_local:
            if verbose:
                console.print("[cyan]Running local test generation...[/cyan]")
            generated_test, total_cost, model_name = run_local_fallback()
        else:
            try:
                if requests is None:
                    raise ImportError("requests module is required for cloud execution.")
                
                jwt_token = CloudConfig.get_jwt_token()
                if not jwt_token:
                    raise ValueError("No JWT token available.")

                url = CloudConfig.get_endpoint_url("generateTest")
                headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
                
                payload = {
                    "promptContent": prompt_content,
                    "codeContent": code_content,
                    "language": detected_language,
                    "strength": eff_strength,
                    "temperature": eff_temperature,
                    "time": eff_time,
                    "verbose": verbose,
                    "sourceFilePath": source_file_path,
                    "testFilePath": test_file_path,
                    "moduleName": module_name,
                    "mode": "increase" if coverage_report else "generate"
                }
                
                if coverage_report:
                    payload["existingTests"] = existing_tests_content
                    payload["coverageReport"] = coverage_report_content

                if verbose:
                    console.print("[cyan]Requesting cloud execution...[/cyan]")
                
                response = requests.post(url, headers=headers, json=payload, timeout=400.0)
                response.raise_for_status()
                data = response.json()
                generated_test = data.get("generatedTest", "")
                total_cost = data.get("totalCost", 0.0)
                model_name = data.get("modelName", "")
                
            except Exception as e:
                console.print(f"[bold yellow]Cloud execution failed ({e}). Falling back to local execution...[/bold yellow]")
                generated_test, total_cost, model_name = run_local_fallback()

        if not generated_test or not generated_test.strip():
            console.print("[bold red]Error: Generated test content is empty.[/bold red]")
            return "", 0.0, "", None, "Error: Generated test content is empty."

        # 7. Write Output
        write_path = output_file
        mode = "w"
        content_to_write = generated_test

        if merge and existing_tests:
            write_path = existing_tests[0]
            mode = "a"
            content_to_write = f"\n\n{generated_test}"

        try:
            out_p = Path(write_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, mode, encoding="utf-8") as f:
                f.write(content_to_write)
        except Exception as e:
            console.print(f"[bold red]Failed to write output file: {e}[/bold red]")
            return "", 0.0, "", None, f"Error: Failed to write output file: {e}"

        return generated_test, total_cost, model_name, None, ""

    except click.Abort:
        raise
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
        return "", 0.0, f"Error: {e}", None, f"Error: {e}"


def main() -> None:
    """CLI entrypoint for legacy/manual test generation."""
    from .commands.generate import test as test_command
    test_command.main(standalone_mode=True)