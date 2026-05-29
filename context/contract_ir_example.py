import sys
import os
from pathlib import Path

# Ensure the pdd package can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdd.contract_ir import (
    parse_prompt_contracts,
    extract_sections,
    extract_rules,
    extract_waivers,
    iter_covers_refs,
    PromptContractIR,
    Rule,
    Waiver
)

def run_example():
    """
    Demonstrates how to use the contract_ir module to parse contract-related sections
    from a prompt file and extract rules, waivers, and coverage references.
    """
    # Create a dummy prompt file for demonstration
    example_prompt_path = Path("example_prompt.prompt")
    example_prompt_content = """
<contract_rules>
- Rule 1: Always be helpful.
- Rule 2: Never leak secrets.
</contract_rules>

<coverage>
This module covers basic contract parsing.
</coverage>

<waivers>
- Waiver 1: No liability for hallucinations.
</waivers>

<vocabulary>
- IR: Intermediate Representation
</vocabulary>

<capabilities>
- Parse XML-like sections.
</capabilities>

<non_responsibilities>
- Executing the contracts.
</non_responsibilities>
"""
    example_prompt_path.write_text(example_prompt_content, encoding="utf-8")

    print("--- Testing parse_prompt_contracts ---")
    print()
    
    try:
        ir = parse_prompt_contracts(example_prompt_path)
        print(f"Rules found: {len(ir.rules)}")
        for rule in ir.rules:
            print(f"  - {rule.text}")
        
        print()
        print(f"Waivers found: {len(ir.waivers)}")
        for waiver in ir.waivers:
            print(f"  - {waiver.text}")
            
        print()
        print(f"Coverage: {ir.coverage}")
        print(f"Vocabulary: {ir.vocabulary}")
        print(f"Capabilities: {ir.capabilities}")
        print(f"Non-responsibilities: {ir.non_responsibilities}")
    finally:
        if example_prompt_path.exists():
            example_prompt_path.unlink()

    print()
    print("--- Testing extract_sections ---")
    print()
    sections = extract_sections(example_prompt_content)
    for key, value in sections.items():
        print(f"{key}: {value[:50]}...")

    print()
    print("--- Testing iter_covers_refs ---")
    print()
    story_text = """
## Covers
- REF-1
- REF-2
* REF-3

## Another Section
- Not a coverage ref.
"""
    print("Coverage references:")
    for ref in iter_covers_refs(story_text):
        print(f"  - {ref}")

if __name__ == "__main__":
    run_example()
