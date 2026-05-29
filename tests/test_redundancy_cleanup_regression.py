import pytest
import os
from pathlib import Path

def test_postprocess_0_cleanup_regression():
    """Verifies that redundant postprocess_0.py and related files are removed."""
    base_dir = Path(__file__).parent.parent
    
    deleted_files = [
        base_dir / "pdd" / "postprocess_0.py",
        base_dir / "prompts" / "postprocess_0_python.prompt",
        base_dir / "tests" / "test_postprocess_0.py"
    ]
    
    for f in deleted_files:
        assert not f.exists(), f"File {f} should have been deleted but still exists."

def test_postprocess_0_import_regression():
    """Verifies that pdd.postprocess_0 cannot be imported as a module."""
    with pytest.raises(ImportError):
        import pdd.postprocess_0

def test_postprocess_0_in_postprocess_regression():
    """Verifies that postprocess_0 logic is now in pdd.postprocess."""
    from pdd.postprocess import postprocess_0
    
    # Test simple extraction logic
    llm_output = "Here is some code:\n```python\nprint('hello')\n```\nAnd more text."
    extracted = postprocess_0(llm_output, "python")
    assert extracted == "print('hello')"
    
    # Test prompt extraction
    llm_output_prompt = "<prompt>\nmy prompt content\n</prompt>"
    extracted_prompt = postprocess_0(llm_output_prompt, "prompt")
    assert extracted_prompt == "my prompt content"
