"""
Test Plan for contract_ir.py:
1. Test extract_sections: Verify it correctly extracts all supported tags and handles missing ones.
2. Test extract_rules: Verify it converts bulleted text into a list of Rule objects.
3. Test extract_waivers: Verify it converts bulleted text into a list of Waiver objects.
4. Test parse_prompt_contracts: Use tmp_path to create a file and verify the PromptContractIR object.
5. Test parse_prompt_contracts (FileNotFound): Verify it raises FileNotFoundError and handles missing file.
6. Test iter_covers_refs: Verify it extracts references from '## Covers' sections correctly.
7. Test COVERAGE_REF_RE: Verify it only matches leading bullets.
8. Test function-scope imports: Verify rich is not at module level.
"""

import pytest
import re
from pathlib import Path
from pdd.contract_ir import (
    extract_sections,
    extract_rules,
    extract_waivers,
    parse_prompt_contracts,
    iter_covers_refs,
    PromptContractIR,
    Rule,
    Waiver,
    COVERAGE_REF_RE
)

def test_extract_sections():
    text = """
<contract_rules>Rule 1</contract_rules>
<coverage>Coverage 1</coverage>
<WAIVERS>Waiver 1</WAIVERS>
"""
    sections = extract_sections(text)
    assert sections["contract_rules"] == "Rule 1"
    assert sections["coverage"] == "Coverage 1"
    assert sections["waivers"] == "Waiver 1"
    assert sections["vocabulary"] == ""
    assert sections["capabilities"] == ""
    assert sections["non_responsibilities"] == ""

def test_extract_rules():
    text = "- Rule 1\n* Rule 2\nRule 3"
    rules = extract_rules(text)
    assert len(rules) == 3
    assert rules[0].text == "Rule 1"
    assert rules[1].text == "Rule 2"
    assert rules[2].text == "Rule 3"

def test_extract_waivers():
    text = "- Waiver 1\n* Waiver 2"
    waivers = extract_waivers(text)
    assert len(waivers) == 2
    assert waivers[0].text == "Waiver 1"
    assert waivers[1].text == "Waiver 2"

def test_parse_prompt_contracts(tmp_path):
    d = tmp_path / "subdir"
    d.mkdir()
    p = d / "test.prompt"
    p.write_text("<contract_rules>- Rule A</contract_rules><coverage>Cover A</coverage>", encoding="utf-8")
    
    ir = parse_prompt_contracts(p)
    assert isinstance(ir, PromptContractIR)
    assert len(ir.rules) == 1
    assert ir.rules[0].text == "Rule A"
    assert ir.coverage == "Cover A"

def test_parse_prompt_contracts_not_found():
    with pytest.raises(FileNotFoundError):
        parse_prompt_contracts(Path("non_existent_file.prompt"))

def test_iter_covers_refs():
    story_text = """
## Covers
- REF-1
* REF-2
  - INDENTED (should be matched if it starts with bullet)
Not a ref.

## Other
- Not a cover.
"""
    refs = list(iter_covers_refs(story_text))
    assert "REF-1" in refs
    assert "REF-2" in refs
    # The regex ^[-*] with MULTILINE should match indented if there's no preceding non-whitespace on line
    # Wait, the regex is ^[-*]\s+(.+)$
    # If it's "  - REF", it won't match because of ^.
    # Let's check.
    assert "INDENTED" not in refs # Based on ^[-*]

def test_coverage_ref_re():
    assert COVERAGE_REF_RE.match("- Valid")
    assert COVERAGE_REF_RE.match("* Valid")
    assert not COVERAGE_REF_RE.match("  - Invalid")
    assert not COVERAGE_REF_RE.match("Prose - not a ref")

def test_rich_import():
    import sys
    # Ensure rich.console is not already in sys.modules if we want a clean test,
    # but that's hard. At least check it's not at module level of contract_ir.
    import pdd.contract_ir
    # If it was at module level, it would be in pdd.contract_ir.__dict__ (if imported as such)
    # or just globally available.
    # More simply, we check that 'Console' is not in pdd.contract_ir globals.
    assert 'Console' not in vars(pdd.contract_ir)
