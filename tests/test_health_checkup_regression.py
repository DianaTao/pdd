"""
Regression tests for Step 6a health checkup fixes.
"""
import importlib
import sys
import os
import pytest
from pathlib import Path
from click.testing import CliRunner
from pdd.cli import cli

def test_import_new_dependencies():
    """Verify that all new dependencies added in Step 6a are importable if installed."""
    deps = [
        "numpy",
        "langchain",
        "langchain_core",
        "langchain_community",
        "langchain_anthropic",
        "langchain_mcp_adapters",
        "langgraph"
    ]
    for dep in deps:
        try:
            importlib.import_module(dep)
        except ImportError as e:
            # We skip if not installed, as we verified they are in manifests
            # and we may not have permission to install in this environment.
            pytest.skip(f"{dep} not installed in this environment.")

def test_firecrawl_import():
    """Verify that firecrawl-py (firecrawl) is importable."""
    try:
        importlib.import_module("firecrawl")
    except ImportError as e:
        pytest.fail(f"Failed to import firecrawl: {e}")

def test_context_init_example_syntax():
    """Verify that context/__init__example.py has no syntax errors."""
    # We add the root to sys.path to import it as a module
    sys.path.append(os.getcwd())
    try:
        import context.__init__example as example
        # Basic check that it has expected content
        assert hasattr(example, "register_commands")
    except SyntaxError as e:
        pytest.fail(f"Syntax error in context/__init__example.py: {e}")
    except ImportError as e:
        pytest.fail(f"Failed to import context.__init__example.py: {e}")
    finally:
        if os.getcwd() in sys.path:
            sys.path.remove(os.getcwd())

def test_no_monkeypatching_in_init():
    """Verify that pdd/__init__.py does not monkeypatch importlib.metadata.distribution."""
    import importlib.metadata
    original_dist = importlib.metadata.distribution
    
    # Import pdd (it should already be imported, but we want to be sure)
    import pdd
    
    # Check if it's still the same
    assert importlib.metadata.distribution is original_dist, "importlib.metadata.distribution has been monkeypatched!"

def test_coverage_cli_interface_smoke():
    """Smoke test for pdd coverage interface flags."""
    runner = CliRunner()
    
    # Test --tests-dir
    result = runner.invoke(cli, ["coverage", "--contracts", "--tests-dir", "tests"])
    # We don't necessarily expect success if the environment isn't set up, 
    # but we expect it to parse arguments.
    assert "No such option: --tests-dir" not in result.output
    
    # Test --quiet
    result = runner.invoke(cli, ["coverage", "--contracts", "--quiet"])
    assert "No such option: --quiet" not in result.output
    
    # Test --verbose
    result = runner.invoke(cli, ["coverage", "--contracts", "--verbose"])
    assert "No such option: --verbose" not in result.output

def test_dependency_alignment_manifests():
    """Verify pyproject.toml and requirements.txt are aligned as claimed in Step 6a."""
    pyproject_path = Path("pyproject.toml")
    requirements_path = Path("requirements.txt")
    
    pyproject_content = pyproject_path.read_text()
    requirements_content = requirements_path.read_text()
    
    deps = [
        "numpy",
        "langchain",
        "langchain-core",
        "langchain-community",
        "langchain-anthropic",
        "langchain-mcp-adapters",
        "langgraph"
    ]
    for dep in deps:
        assert dep in pyproject_content, f"{dep} missing from pyproject.toml"
        assert dep in requirements_content, f"{dep} missing from requirements.txt"
    
    # Check for litellm version alignment
    assert "litellm[caching]>=1.80.0" in pyproject_content
    assert "litellm[caching]>=1.80.0" in requirements_content
    
    # Check for firecrawl-py naming
    assert "firecrawl-py" in pyproject_content
    assert "firecrawl-py" in requirements_content

def test_cloud_dependencies_in_extra():
    """Verify cloud dependencies are moved to extra in pyproject.toml."""
    pyproject_content = Path("pyproject.toml").read_text()
    
    # Should NOT be in main dependencies section
    # Find the dependencies list in pyproject.toml
    import re
    deps_match = re.search(r"dependencies = \[(.*?)\]", pyproject_content, re.DOTALL)
    if deps_match:
        main_deps = deps_match.group(1)
        assert "boto3" not in main_deps
        assert "google-cloud-aiplatform" not in main_deps
        assert "firebase_admin" not in main_deps
    
    # Should be in optional-dependencies.cloud
    assert "[project.optional-dependencies]" in pyproject_content
    cloud_section = pyproject_content.split("cloud = [")[1].split("]")[0]
    assert "boto3" in cloud_section
    assert "google-cloud-aiplatform" in cloud_section
    assert "firebase_admin" in cloud_section
