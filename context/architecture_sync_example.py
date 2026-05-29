"""
Example usage of the architecture_sync module for bidirectional sync
between architecture.json and prompt files using PDD metadata tags.
"""

import sys
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure we can import from the parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdd.architecture_sync import (
    parse_prompt_tags,
    update_architecture_from_prompt,
    sync_all_prompts_to_architecture,
    sync_prompts_to_architecture,
    validate_dependencies,
    validate_interface_structure,
    get_architecture_entry_for_prompt,
    has_pdd_tags,
    generate_tags_from_architecture,
)

# --- Setup Mock Environment ---
def setup_mock_files(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    
    arch_file = tmp_path / "architecture.json"
    
    # Create a dummy prompt
    prompt_content = """<pdd-reason>Handles user authentication</pdd-reason>
<pdd-interface>
{
  "type": "module",
  "module": {
    "functions": [{"name": "login", "signature": "(user, pwd)", "returns": "bool"}]
  }
}
</pdd-interface>
<pdd-dependency>db_python.prompt</pdd-dependency>

% Role & Scope
...
"""
    (prompts_dir / "auth_python.prompt").write_text(prompt_content)
    (prompts_dir / "db_python.prompt").write_text("<pdd-reason>Database</pdd-reason>")
    
    # Create architecture.json
    arch_data = [
        {
            "filename": "auth_python.prompt",
            "filepath": "pdd/auth.py",
            "reason": "Old reason",
            "dependencies": []
        }
    ]
    arch_file.write_text(json.dumps(arch_data, indent=2))
    
    return prompts_dir, arch_file

# --- Example 1: Parse PDD tags from prompt content ---
def example_parse_tags():
    """Parse PDD metadata tags from prompt content."""
    prompt_content = """
<pdd-reason>Handles user authentication and session management</pdd-reason>

<pdd-interface>
{
  "type": "module",
  "module": {
    "functions": [
      {"name": "authenticate", "signature": "(username: str, password: str) -> Optional[User]", "returns": "Optional[User]"},
      {"name": "create_session", "signature": "(user: User) -> str", "returns": "str"}
    ]
  }
}
</pdd-interface>

<pdd-dependency>database_python.prompt</pdd-dependency>
<pdd-dependency>config_python.prompt</pdd-dependency>

% Role & Scope
Your goal is to implement user authentication...
"""

    tags = parse_prompt_tags(prompt_content)

    print("--- Example 1: parse_prompt_tags ---")
    print(f"Reason: {tags['reason']}")
    print(f"Interface type: {tags['interface']['type']}")
    print(f"Dependencies: {tags['dependencies']}")
    print(f"Has dependency tags: {tags['has_dependency_tags']}")
    print()

# --- Example 2: Update architecture.json from a single prompt ---
def example_update_single_prompt(prompts_dir, arch_file):
    """Update architecture.json from a single prompt file's PDD tags."""
    print("--- Example 2: update_architecture_from_prompt ---")
    result = update_architecture_from_prompt(
        prompt_filename="auth_python.prompt",
        prompts_dir=prompts_dir,
        architecture_path=arch_file,
        dry_run=False
    )

    if result['success']:
        print(f"Updated: {result['updated']}")
        print(f"Changes: {result['changes']}")
    else:
        print(f"Error: {result['error']}")
    print()

# --- Example 3: Sync all prompts to architecture.json ---
def example_sync_all(prompts_dir, arch_file):
    """Sync all prompt files to architecture.json."""
    print("--- Example 3: sync_all_prompts_to_architecture ---")
    result = sync_all_prompts_to_architecture(
        prompts_dir=prompts_dir,
        architecture_path=arch_file,
        dry_run=True  # Preview changes
    )

    print(f"Success: {result['success']}")
    print(f"Updated: {result['updated_count']} modules")
    print(f"Registered: {result['registered']}")
    print()

# --- Example 4: Validate dependencies ---
def example_validate_dependencies(prompts_dir):
    """Validate that all dependencies exist and are unique."""
    print("--- Example 4: validate_dependencies ---")
    dependencies = [
        "auth_python.prompt",
        "missing_file.prompt",
        "auth_python.prompt",
    ]

    result = validate_dependencies(dependencies, prompts_dir=prompts_dir)

    print(f"Valid: {result['valid']}")
    print(f"Missing files: {result['missing']}")
    print(f"Duplicates: {result['duplicates']}")
    print()

# --- Example 5: Validate interface structure ---
def example_validate_interface():
    """Validate interface JSON structure."""
    print("--- Example 5: validate_interface_structure ---")
    # Valid module interface
    valid_interface = {
        "type": "module",
        "module": {
            "functions": [
                {"name": "process", "signature": "(data: Dict) -> Dict", "returns": "Dict"}
            ]
        }
    }

    result = validate_interface_structure(valid_interface)
    print(f"Valid interface: {result['valid']}")

    # Invalid interface (missing nested key)
    invalid_interface = {
        "type": "module"
    }

    result = validate_interface_structure(invalid_interface)
    print(f"Invalid interface valid: {result['valid']}")
    print(f"Errors: {result['errors']}")
    print()

# --- Example 6: Generate tags from architecture entry ---
def example_generate_tags():
    """Generate PDD tags from an architecture.json entry."""
    print("--- Example 6: generate_tags_from_architecture ---")
    arch_entry = {
        "reason": "Handles user auth",
        "interface": {"type": "module", "module": {"functions": []}},
        "dependencies": ["db_python.prompt"]
    }

    tags = generate_tags_from_architecture(arch_entry)
    print("Generated tags:")
    print(tags)
    print()

if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        p_dir, a_file = setup_mock_files(tmp_path)
        
        print("=== Architecture Sync Examples ===\n")
        
        example_parse_tags()
        example_update_single_prompt(p_dir, a_file)
        example_sync_all(p_dir, a_file)
        example_validate_dependencies(p_dir)
        example_validate_interface()
        example_generate_tags()
        
    sys.exit(0)
