import sys
import os
import json
from unittest.mock import MagicMock, patch

# Ensure the project root is in sys.path so we can import pdd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

# Mock the dependencies of the module we are about to import
# This is necessary because they might import other things that are not present
mock_architecture_sync = MagicMock()
mock_agentic_common = MagicMock()
mock_load_prompt_template = MagicMock()
mock_app = MagicMock()

sys.modules["pdd.architecture_sync"] = mock_architecture_sync
sys.modules["pdd.agentic_common"] = mock_agentic_common
sys.modules["pdd.load_prompt_template"] = mock_load_prompt_template
sys.modules["pdd.server.app"] = mock_app

# Now import the module under test
from pdd.server.routes.architecture import (
    ArchitectureModule,
    ValidateArchitectureRequest,
    _validate_architecture,
)

def demonstrate_validation():
    """
    Demonstrates how to use the validation logic.
    
    Inputs:
        modules: List of ArchitectureModule objects
        
    Outputs:
        ValidationResult: Object containing 'valid' boolean, 'errors' and 'warnings' lists.
    """
    print("--- Architecture Validation Demo ---")
    print()

    # 1. Valid Architecture
    valid_modules = [
        ArchitectureModule(
            filename="core.py",
            filepath="src/core.py",
            description="Core logic",
            reason="Foundation",
            priority=10,
            dependencies=[]
        ),
        ArchitectureModule(
            filename="api.py",
            filepath="src/api.py",
            description="API endpoints",
            reason="Interface",
            priority=5,
            dependencies=["core.py"]
        )
    ]
    
    result = _validate_architecture(valid_modules)
    print(f"Valid case: valid={result.valid}, errors={len(result.errors)}, warnings={len(result.warnings)}")
    print()

    # 2. Circular Dependency
    circular_modules = [
        ArchitectureModule(
            filename="A.py",
            filepath="src/A.py",
            description="Module A",
            reason="Cycle test",
            priority=1,
            dependencies=["B.py"]
        ),
        ArchitectureModule(
            filename="B.py",
            filepath="src/B.py",
            description="Module B",
            reason="Cycle test",
            priority=1,
            dependencies=["A.py"]
        )
    ]
    
    result = _validate_architecture(circular_modules)
    print(f"Circular case: valid={result.valid}")
    for err in result.errors:
        print(f"  [Error] {err.type}: {err.message}")
    print()

    # 3. Missing Dependency and Orphan Warning
    mixed_modules = [
        ArchitectureModule(
            filename="orphan.py",
            filepath="src/orphan.py",
            description="Lonely",
            reason="Test",
            priority=1,
            dependencies=[]
        ),
        ArchitectureModule(
            filename="broken.py",
            filepath="src/broken.py",
            description="Missing link",
            reason="Test",
            priority=1,
            dependencies=["non_existent.py"]
        )
    ]
    
    result = _validate_architecture(mixed_modules)
    print(f"Mixed case: valid={result.valid}")
    for err in result.errors:
        print(f"  [Error] {err.type}: {err.message}")
    for warn in result.warnings:
        print(f"  [Warning] {warn.type}: {warn.message}")
    print()

if __name__ == "__main__":
    try:
        demonstrate_validation()
    except Exception as e:
        print(f"Example failed: {e}")
        sys.exit(1)
    
    sys.exit(0)
