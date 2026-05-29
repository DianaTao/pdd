import pytest
from pdd.agentic_common import extract_step_report

def test_extract_step_report_regression():
    """Verifies that extract_step_report is correctly exported and functional."""
    report_content = "## Step Report\nSome findings."
    text = f"Some preamble.\n<step_report>\n{report_content}\n</step_report>\nPostamble."
    
    extracted = extract_step_report(text)
    assert extracted == report_content

def test_extract_step_report_no_tag():
    """Verifies extract_step_report returns None when no tag is present."""
    text = "No report here."
    assert extract_step_report(text) is None

def test_extract_step_report_empty():
    """Verifies extract_step_report handles empty input."""
    assert extract_step_report("") is None
    assert extract_step_report(None) is None

def test_extract_step_report_multiple_tags():
    """Verifies extract_step_report extracts the LAST tag."""
    text = "<step_report>Report 1</step_report> <step_report>Report 2</step_report>"
    assert extract_step_report(text) == "Report 2"
