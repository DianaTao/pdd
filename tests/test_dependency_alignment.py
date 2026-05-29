import re
from pathlib import Path

def test_litellm_version_alignment():
    """Verify that litellm version in requirements.txt aligns with pyproject.toml (Issue #1152)."""
    root = Path(__file__).parent.parent
    
    requirements_path = root / "requirements.txt"
    pyproject_path = root / "pyproject.toml"
    
    # Read requirements.txt
    req_content = requirements_path.read_text(encoding="utf-8")
    # Search for litellm[...][<=]{1,2}X.Y.Z or similar
    # Handles extras like [caching] and multiple constraints like >=1.80.0,<=1.82.6
    req_match = re.search(r"litellm(?:\[.*?\])?.*?(?:<=|==)([\d\.]+)", req_content)
    assert req_match, "litellm not found in requirements.txt"
    req_version = req_match.group(1)
    
    # Read pyproject.toml
    pyproject_content = pyproject_path.read_text(encoding="utf-8")
    # Search for "litellm[...][<=]{1,2}X.Y.Z" or litellm = "..."
    pyproject_match = re.search(r'litellm(?:\[.*?\])?.*?(?:<=|==)([\d\.]+)', pyproject_content)
    assert pyproject_match, "litellm not found in pyproject.toml"
    pyproject_version = pyproject_match.group(1)
    
    assert req_version == pyproject_version, (
        f"litellm version mismatch: requirements.txt ({req_version}) != "
        f"pyproject.toml ({pyproject_version})"
    )
