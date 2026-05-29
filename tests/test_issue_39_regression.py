
import os
from pathlib import Path
import json
import pytest
from pdd.user_story_tests import _prompt_summary_line, _render_story_markdown_from_prompts

def test_removed_problematic_prompt():
    """Verify that the problematic prompt was removed to prevent architecture drift."""
    problematic_prompt = Path("pdd/prompts/issue_820_user_story_template_python.prompt")
    assert not problematic_prompt.exists(), "Problematic prompt file should have been removed."

def test_user_story_tests_prompt_requirements():
    """Verify that user_story_tests_python.prompt contains the new requirements."""
    prompt_path = Path("pdd/prompts/user_story_tests_python.prompt")
    assert prompt_path.exists()
    content = prompt_path.read_text()
    
    required_sections = [
        "## Story",
        "## Prompt Scope",
        "## Covers",
        "## Oracle",
        "## Non-Oracle",
        "## Negative Cases",
        "seed from `contract_ir`"
    ]
    for section in required_sections:
        assert section in content, f"Requirement '{section}' missing from user_story_tests_python.prompt"

def test_architecture_registration():
    """Verify that pdd/user_story_tests.py is registered in architecture.json."""
    arch_path = Path("architecture.json")
    assert arch_path.exists()
    with open(arch_path, "r") as f:
        arch = json.load(f)
    
    # arch is a list of module definitions
    found = any(m.get("filepath") == "pdd/user_story_tests.py" for m in arch)
    assert found, "pdd/user_story_tests.py not found in architecture.json"

def test_summary_line_truncation(tmp_path):
    """Verify that _prompt_summary_line truncates lines to 80 characters."""
    long_line = "A" * 100
    test_file = tmp_path / "test.prompt"
    test_file.write_text(long_line)
    
    summary = _prompt_summary_line(test_file)
    assert len(summary) <= 80
    assert summary.endswith("...")
    assert summary == "A" * 77 + "..."

def test_summary_line_exception_handling():
    """Verify that _prompt_summary_line handles missing files gracefully."""
    non_existent = Path("non_existent_file.prompt")
    summary = _prompt_summary_line(non_existent)
    assert summary == "Prompt included in story scope."

def test_markdown_rendering_sections(tmp_path):
    """Verify that _render_story_markdown_from_prompts includes all required sections."""
    title = "Test Story"
    p1 = tmp_path / "test_python.prompt"
    p1.write_text("Test prompt content")
    
    markdown = _render_story_markdown_from_prompts(
        title=title,
        prompt_paths=[p1],
        prompts_root=tmp_path
    )
    
    expected_sections = [
        "## Story",
        "## Prompt Scope",
        "## Covers",
        "## Oracle",
        "## Non-Oracle",
        "## Negative Cases",
        "## Acceptance Criteria"
    ]
    for section in expected_sections:
        assert section in markdown, f"Section '{section}' missing from rendered markdown"
    
    assert f"# User Story: {title}" in markdown
    assert "- `test_python.prompt`: Test prompt content" in markdown

def test_rich_import_placement():
    """Verify that 'rich' is not imported at the top level of pdd/user_story_tests.py."""
    filepath = Path("pdd/user_story_tests.py")
    content = filepath.read_text()
    
    # Check that 'from rich' or 'import rich' is not at the start of a line at top level
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import rich") or stripped.startswith("from rich"):
            # Ensure it's inside a function (indented)
            assert line.startswith("    "), f"rich import found at top level: {line}"

def test_architecture_no_duplicate_dependencies():
    """Verify that no module in architecture.json has duplicate dependencies."""
    arch_path = Path("architecture.json")
    with open(arch_path, "r") as f:
        arch = json.load(f)
    
    for module in arch:
        deps = module.get("dependencies", [])
        assert len(deps) == len(set(deps)), f"Duplicate dependencies found in module: {module.get('filename')}"

def test_evidence_manifest_filename_no_prefix():
    """Verify that evidence_manifest_python.prompt does not have an incorrect 'pdd/' prefix."""
    arch_path = Path("architecture.json")
    with open(arch_path, "r") as f:
        arch = json.load(f)
    
    for module in arch:
        if "evidence_manifest" in module.get("filename", ""):
            filename = module.get("filename")
            assert not filename.startswith("pdd/"), f"Filename '{filename}' should not have 'pdd/' prefix"

def test_change_main_rich_import_placement():
    """Verify that 'rich' is not imported at the top level of pdd/change_main.py."""
    filepath = Path("pdd/change_main.py")
    content = filepath.read_text()
    
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import rich") or stripped.startswith("from rich"):
            assert line.startswith("    "), f"rich import found at top level in change_main.py: {line}"

def test_change_main_docstring_syntax():
    """Verify that the docstring in pdd/change_main.py is valid and can be parsed."""
    import ast
    filepath = Path("pdd/change_main.py")
    content = filepath.read_text()
    tree = ast.parse(content)
    
    # Find change_main function
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "change_main":
            docstring = ast.get_docstring(node)
            assert docstring is not None
            assert "Args:" in docstring
            assert "Returns:" in docstring
            # Verify no indentation error in Args block (implicit in ast.parse success)
            break
    else:
        pytest.fail("change_main function not found in pdd/change_main.py")

def test_frontend_checkup_split_views():
    """Verify that 'checkup' and 'split' views are implemented in pdd/frontend/App.tsx."""
    filepath = Path("pdd/frontend/App.tsx")
    if not filepath.exists():
        pytest.skip("Frontend file not found")
        
    content = filepath.read_text()
    
    assert "'checkup'" in content
    assert "'split'" in content
    # Check for icons added in Step 6a
    assert "ShieldCheckIcon" in content
    assert "ScissorsIcon" in content
    # Check for navigation/rendering logic
    assert "view === 'checkup'" in content
    assert "view === 'split'" in content
