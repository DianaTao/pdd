import json
from pathlib import Path
import re


def test_firebase_admin_removed():
    """Verify that firebase_admin is removed from dependencies."""
    pyproject = Path("pyproject.toml").read_text()
    assert "firebase_admin" not in pyproject

    requirements = Path("requirements.txt").read_text()
    assert "firebase_admin" not in requirements

    # Check audit_deps.py mapping
    audit_deps = Path("audit_deps.py").read_text()
    assert "firebase_admin" not in audit_deps


def test_z3_solver_moved_to_dev():
    """Verify that z3-solver is in dev dependencies, not production."""
    pyproject = Path("pyproject.toml").read_text()
    # Should not be in main dependencies
    deps_match = re.search(r"dependencies = \[(.*?)\]", pyproject, re.DOTALL)
    if deps_match:
        assert "z3-solver" not in deps_match.group(1)

    # Should be in dev optional-dependencies
    assert '"z3-solver==4.16.0.0"' in pyproject
    assert "[project.optional-dependencies]" in pyproject

    requirements = Path("requirements.txt").read_text()
    # Should be under # Dev dependencies
    dev_section = requirements.split("# Dev dependencies")[-1]
    assert "z3-solver==4.16.0.0" in dev_section
    # Should NOT be in production section
    prod_section = requirements.split("# Dev dependencies")[0]
    assert "z3-solver" not in prod_section


def test_architecture_paths_fixed():
    """Verify that architecture.json has correct paths for moved files."""
    with open("architecture.json", "r") as f:
        arch = json.load(f)

    found_run_generated = False
    found_prompt_tester = False

    for entry in arch:
        if entry.get("filename") == "run_generated_python.prompt":
            assert entry.get("filepath") == "utils/run_generated.py"
            found_run_generated = True
        if entry.get("filename") == "prompt_tester_python.prompt":
            assert entry.get("filepath") == "tests/prompt_tester.py"
            found_prompt_tester = True

    assert found_run_generated, "run_generated_python.prompt entry not found"
    assert found_prompt_tester, "prompt_tester_python.prompt entry not found"


def test_agentic_bug_prompts_synchronized():
    """Verify that all 12 agentic_bug_step prompts are correctly listed in architecture.json."""
    with open("architecture.json", "r") as f:
        arch = json.load(f)

    steps = {}
    for entry in arch:
        filename = entry.get("filename", "")
        if filename.startswith("agentic_bug_step") and "_LLM.prompt" in filename:
            # Extract step number
            match = re.search(r"step(\d+)", filename)
            if match:
                step_num = int(match.group(1))
                steps[step_num] = entry

    assert len(steps) == 12
    for i in range(1, 13):
        assert i in steps
        # Check some specific one mentioned in fixes
        if i == 5:
            assert "reproduce" in steps[i]["filename"]
        if i == 4:
            assert "api_research" in steps[i]["filename"]


def test_audit_scripts_consistency():
    """Verify audit scripts don't have stale firebase_admin references."""
    audit_deps = Path("audit_deps.py").read_text()
    assert "firebase_admin" not in audit_deps

    final_check = Path("final_missing_check.py").read_text()
    assert "firebase_admin" not in final_check
