import pdd

def test_init_exports_regression():
    """Verify that extract_step_report is exported in pdd/__init__.py."""
    assert hasattr(pdd, "extract_step_report")
    assert callable(pdd.extract_step_report)
