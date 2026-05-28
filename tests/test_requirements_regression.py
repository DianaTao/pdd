from pathlib import Path

def test_requirements_standardization_regression():
    """Verify that requirements.txt uses hyphens for key packages."""
    req_path = Path("requirements.txt")
    content = req_path.read_text()
    
    assert "firecrawl-py" in content
    assert "z3-solver" in content
    assert "firecrawl_py" not in content
    assert "z3_solver" not in content
