import sys
import os
from pathlib import Path

# sys.path setup so the import resolves
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdd.coverage_contracts import build_coverage, build_coverage_directory

def setup_mock_environment(base_dir: Path):
    """Sets up a mock environment with prompts, stories, and tests."""
    prompts_dir = base_dir / "prompts"
    stories_dir = base_dir / "stories"
    tests_dir = base_dir / "tests"
    
    for d in [prompts_dir, stories_dir, tests_dir]:
        d.mkdir(parents=True, exist_ok=True)
        
    # Create a prompt with contract rules
    prompt_path = prompts_dir / "example.prompt"
    prompt_path.write_text("""
<contract_rules>
R1 - Requirement One
R2 - Requirement Two
R3 - Requirement Three
R4 - Waived Requirement
</contract_rules>

<waivers>
W1:
  Rule: R4
  Reason: This is waived for demo purposes.
</waivers>

<coverage>
- R1: story__example.md
</coverage>
""", encoding="utf-8")

    # Create a story linked to the prompt
    # Use 'example.prompt' in metadata to ensure match
    story_path = stories_dir / "story__example.md"
    story_path.write_text("""
<!-- pdd-story-prompts: example.prompt -->
## Covers
- R1: rule 1
- R2: rule 2

## Acceptance Criteria
- Verified R1
- Verified R2
""", encoding="utf-8")

    # Create a test referencing a rule
    test_path = tests_dir / "test_example.py"
    test_path.write_text("""
def test_R1_feature():
    # Covers R1
    assert True
""", encoding="utf-8")

    return prompt_path, prompts_dir, stories_dir, tests_dir

def main():
    # Use a local temp directory for mocks
    base_dir = Path(os.path.dirname(__file__)) / "mock_env"
    if base_dir.exists():
        import shutil
        shutil.rmtree(base_dir)
    base_dir.mkdir()
    
    try:
        prompt_path, prompts_dir, stories_dir, tests_dir = setup_mock_environment(base_dir)
        
        print("--- Testing build_coverage ---")
        result = build_coverage(prompt_path, stories_dir=stories_dir, tests_dir=tests_dir)
        
        print(f"Prompt: {result.prompt_path}")
        print(f"Legacy Safe: {result.legacy_safe}")
        
        for rule in result.rules:
            print(f"Rule {rule.rule_id}: {rule.status}")
            print(f"  Description: {rule.description}")
            if rule.stories:
                print(f"  Stories: {', '.join(rule.stories)}")
            if rule.tests:
                print(f"  Tests: {', '.join(rule.tests)}")
            if rule.waiver:
                print(f"  Waiver: {rule.waiver}")
            if rule.failures:
                print(f"  Failures: {', '.join(rule.failures)}")
        
        print()
        print("--- Testing build_coverage_directory ---")
        results = build_coverage_directory(prompts_dir, stories_dir=stories_dir, tests_dir=tests_dir)
        print(f"Found {len(results)} prompt(s) in directory.")
        
    finally:
        # Clean up
        import shutil
        if base_dir.exists():
            shutil.rmtree(base_dir)

if __name__ == "__main__":
    main()
