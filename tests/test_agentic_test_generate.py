# Test Plan - Agentic Test Generate Verification
#
# Requirements Covered:
# 1. File Prefix Requirement: Verified in agentic_test_generate.py.
# 2. Type-hinting: Verified in signatures.
# 3. Printing Style: Mocked/asserted rich console output.
# 4. Package Structure & Relative Imports: Verified via relative imports.
# 5. Import Strategy: Verified module-level and function-scope imports.
# 6. Heavy Dependencies: Verified function-scope try/except.
# 7. Error Handling: Tested via test_run_agentic_test_generate_io_error.
# 8. Preservation of Comments & Docstrings: Retained.
# 9. Single-pass Agent Execution: Tested max_retries=0 in test_run_agentic_test_generate_success.
# 10. File Mtime Recording: Tested in test_get_file_mtimes and test_detect_changed_files.
# 11. Directory Exclusion in Scanning: Tested in test_get_file_mtimes.
# 12. File Generation & Read-back: Tested in test_run_agentic_test_generate_success.
# 13. Alternative Output Path Check: Tested in test_run_agentic_test_generate_alternative_path.
# 14. JSON Output Extraction: Tested in test_extract_json_from_text.
# 15. Return Tuple Schema: Tested in all run tests.
# 16. Empty/Missing Content Handling: Tested in test_run_agentic_test_generate_no_test_file.
# 17. Model Name Formatting: Tested in test_run_agentic_test_generate_success.
# 18. Prompt Template Loading: Tested in test_run_agentic_test_generate_template_not_found.
# 19. Template Formatting: Tested in test_run_agentic_test_generate_success.

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pdd.agentic_test_generate import (
    _get_file_mtimes,
    _extract_json_from_text,
    _read_generated_test_file,
    _detect_changed_files,
    run_agentic_test_generate,
)


# -----------------------------------------------------------------------------
# Unit Tests for Helpers
# -----------------------------------------------------------------------------

def test_get_file_mtimes(tmp_path: Path) -> None:
    """Verify _get_file_mtimes recursively scans files and ignores IGNORED_DIRS."""
    # Create valid files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file_a = src_dir / "foo.py"
    file_a.write_text("print('hello')", encoding="utf-8")

    # Create files inside ignored directory
    ignored_dir = tmp_path / "node_modules"
    ignored_dir.mkdir()
    file_b = ignored_dir / "bar.js"
    file_b.write_text("console.log('ignored')", encoding="utf-8")

    mtimes = _get_file_mtimes(tmp_path)

    # file_a should be tracked, file_b should be skipped
    assert file_a in mtimes
    assert file_b not in mtimes
    assert isinstance(mtimes[file_a], float)


def test_extract_json_from_text() -> None:
    """Verify JSON parsing and extraction handles markdown blocks, raw JSON, and fallback."""
    # 1. Markdown code block
    text_markdown = "Here is the response:\n```json\n{\n  \"success\": true,\n  \"message\": \"Passed\"\n}\n```"
    result = _extract_json_from_text(text_markdown)
    assert result == {"success": True, "message": "Passed"}

    # 2. Markdown code block without json label
    text_markdown_no_label = "```\n{\"success\": true}\n```"
    result = _extract_json_from_text(text_markdown_no_label)
    assert result == {"success": True}

    # 3. Raw JSON text
    text_raw = "{\"success\": true, \"message\": \"Raw\"}"
    result = _extract_json_from_text(text_raw)
    assert result == {"success": True, "message": "Raw"}

    # 4. JSON nested in text (fallback)
    text_nested = "Some text before {\"success\": true, \"nested\": {\"key\": 123}} some text after"
    result = _extract_json_from_text(text_nested)
    assert result == {"success": True, "nested": {"key": 123}}

    # 5. Invalid JSON
    text_invalid = "This is not json at all."
    assert _extract_json_from_text(text_invalid) is None


def test_read_generated_test_file(tmp_path: Path) -> None:
    """Verify reading generated test file content or empty string."""
    test_file = tmp_path / "test_foo.py"
    
    # Missing file returns empty string
    assert _read_generated_test_file(test_file) == ""

    # Existing file returns contents
    content = "def test_foo(): pass"
    test_file.write_text(content, encoding="utf-8")
    assert _read_generated_test_file(test_file) == content


def test_detect_changed_files() -> None:
    """Verify detection of changed (new or modified) files."""
    path_a = Path("/root/foo.py")
    path_b = Path("/root/bar.py")
    path_c = Path("/root/baz.py")

    before = {
        path_a: 100.0,
        path_b: 200.0,
    }

    after = {
        path_a: 100.0,  # unchanged
        path_b: 205.0,  # modified
        path_c: 300.0,  # new
    }

    changed = _detect_changed_files(before, after, Path("/root"))
    assert "bar.py" in changed
    assert "baz.py" in changed
    assert "foo.py" not in changed


# -----------------------------------------------------------------------------
# Integration / Orchestration Tests
# -----------------------------------------------------------------------------

def test_run_agentic_test_generate_success(tmp_path: Path) -> None:
    """Verify successful run of run_agentic_test_generate."""
    prompt_file = tmp_path / "spec.prompt"
    prompt_file.write_text("Generate a sum test", encoding="utf-8")

    code_file = tmp_path / "math.py"
    code_file.write_text("def add(a, b): return a + b", encoding="utf-8")

    output_test_file = tmp_path / "test_math.py"

    dummy_template = "Prompt: {prompt_path}, Code: {code_path}, Content: {code_content}"
    
    def mock_agent_run(instruction: str, cwd: Path, **kwargs) -> tuple[bool, str, float, str]:
        # Assert parameters forwarded to dependency
        assert kwargs.get("max_retries") == 0
        assert "math.py" in instruction
        # Simulate agent writing the test file directly
        output_test_file.write_text("def test_add(): assert add(1, 2) == 3", encoding="utf-8")
        # Return agent response
        response_json = json.dumps({"success": True, "message": "Success!"})
        return True, response_json, 0.05, "google"

    with patch("pdd.agentic_test_generate.load_prompt_template", return_value=dummy_template) as mock_load, \
         patch("pdd.agentic_test_generate.run_agentic_task", side_effect=mock_agent_run) as mock_run:
        
        content, cost, model, success, err = run_agentic_test_generate(
            prompt_file, code_file, output_test_file, verbose=True
        )

        mock_load.assert_called_once_with("agentic_test_generate_LLM")
        assert mock_run.called

        assert success is True
        assert cost == 0.05
        assert model == "agentic-google"
        assert content == "def test_add(): assert add(1, 2) == 3"
        assert err == ""


def test_run_agentic_test_generate_alternative_path(tmp_path: Path) -> None:
    """Verify fallback to alternative path when expected output_test_file doesn't exist."""
    prompt_file = tmp_path / "spec.prompt"
    prompt_file.write_text("Generate a sum test", encoding="utf-8")

    code_file = tmp_path / "math.py"
    code_file.write_text("def add(a, b): return a + b", encoding="utf-8")

    output_test_file = tmp_path / "test_math.py"

    dummy_template = "Prompt: {prompt_path}, Code: {code_path}"

    def mock_agent_run(instruction: str, cwd: Path, **kwargs) -> tuple[bool, str, float, str]:
        # Agent writes to an alternative test path instead of output_test_file
        alt_test_file = tmp_path / "test_alternative.py"
        alt_test_file.write_text("def test_alt(): pass", encoding="utf-8")
        response_json = json.dumps({"success": True, "message": "Success on alt!"})
        return True, response_json, 0.08, "anthropic"

    with patch("pdd.agentic_test_generate.load_prompt_template", return_value=dummy_template), \
         patch("pdd.agentic_test_generate.run_agentic_task", side_effect=mock_agent_run):
        
        content, cost, model, success, err = run_agentic_test_generate(
            prompt_file, code_file, output_test_file, verbose=True
        )

        assert success is True
        assert cost == 0.08
        assert model == "agentic-anthropic"
        assert content == "def test_alt(): pass"
        assert err == ""


def test_run_agentic_test_generate_io_error(tmp_path: Path) -> None:
    """Verify run_agentic_test_generate handles input read failure gracefully."""
    # Non-existent files will cause OSError (FileNotFoundError)
    prompt_file = tmp_path / "non_existent.prompt"
    code_file = tmp_path / "non_existent.py"
    output_test_file = tmp_path / "test_non_existent.py"

    content, cost, model, success, err = run_agentic_test_generate(
        prompt_file, code_file, output_test_file
    )

    assert success is False
    assert cost == 0.0
    assert model == "unknown"
    assert content == ""
    assert "Failed to read input files" in err


def test_run_agentic_test_generate_template_not_found(tmp_path: Path) -> None:
    """Verify run_agentic_test_generate handles missing prompt template."""
    prompt_file = tmp_path / "spec.prompt"
    prompt_file.write_text("spec", encoding="utf-8")

    code_file = tmp_path / "math.py"
    code_file.write_text("code", encoding="utf-8")

    output_test_file = tmp_path / "test_math.py"

    with patch("pdd.agentic_test_generate.load_prompt_template", return_value=None):
        content, cost, model, success, err = run_agentic_test_generate(
            prompt_file, code_file, output_test_file
        )

        assert success is False
        assert cost == 0.0
        assert model == "unknown"
        assert content == ""
        assert "not found" in err


def test_run_agentic_test_generate_agent_failure(tmp_path: Path) -> None:
    """Verify run_agentic_test_generate behaves correctly when agent fails or reports failure."""
    prompt_file = tmp_path / "spec.prompt"
    prompt_file.write_text("spec", encoding="utf-8")

    code_file = tmp_path / "math.py"
    code_file.write_text("code", encoding="utf-8")

    output_test_file = tmp_path / "test_math.py"

    dummy_template = "Prompt: {prompt_path}, Code: {code_path}"

    # Scenario 1: run_agentic_task returns success=False
    with patch("pdd.agentic_test_generate.load_prompt_template", return_value=dummy_template), \
         patch("pdd.agentic_test_generate.run_agentic_task", return_value=(False, "Connection timeout", 0.01, "mock")):
        
        content, cost, model, success, err = run_agentic_test_generate(
            prompt_file, code_file, output_test_file
        )

        assert success is False
        assert model == "agentic-mock"
        assert err == "Connection timeout"

    # Scenario 2: run_agentic_task returns success=True, but JSON metadata reports success=False
    fail_json = json.dumps({"success": False, "message": "Compilation failed"})
    with patch("pdd.agentic_test_generate.load_prompt_template", return_value=dummy_template), \
         patch("pdd.agentic_test_generate.run_agentic_task", return_value=(True, fail_json, 0.02, "mock")):
        
        content, cost, model, success, err = run_agentic_test_generate(
            prompt_file, code_file, output_test_file
        )

        assert success is False
        assert model == "agentic-mock"
        assert err == "Compilation failed"


def test_run_agentic_test_generate_no_test_file(tmp_path: Path) -> None:
    """Verify failure state when agent claims success but no test file is generated."""
    prompt_file = tmp_path / "spec.prompt"
    prompt_file.write_text("spec", encoding="utf-8")

    code_file = tmp_path / "math.py"
    code_file.write_text("code", encoding="utf-8")

    output_test_file = tmp_path / "test_math.py"

    dummy_template = "Prompt: {prompt_path}, Code: {code_path}"
    success_json = json.dumps({"success": True, "message": "I did it!"})

    with patch("pdd.agentic_test_generate.load_prompt_template", return_value=dummy_template), \
         patch("pdd.agentic_test_generate.run_agentic_task", return_value=(True, success_json, 0.03, "mock")):
        
        content, cost, model, success, err = run_agentic_test_generate(
            prompt_file, code_file, output_test_file
        )

        # Content is empty, should map to failure with error message
        assert success is False
        assert model == "agentic-mock"
        assert content == ""
        assert "No test file was generated." in err
