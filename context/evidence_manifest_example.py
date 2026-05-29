import sys
import os
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdd.evidence_manifest import write_evidence_manifest, validation_from_sync

def main():
    """
    Example usage of the evidence_manifest module.
    """
    print("PDD Evidence Manifest Example")
    print()

    # Mock project layout
    workspace_dir = Path(os.path.dirname(__file__)) / "tmp_workspace_example"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    prompts_dir = workspace_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    
    src_dir = workspace_dir / "src"
    src_dir.mkdir(exist_ok=True)
    
    # Create prompt file
    prompt_file = prompts_dir / "auth_python.prompt"
    prompt_file.write_text("Update the auth service to use JWT.", encoding="utf-8")
    
    # Create output file
    auth_service_path = src_dir / "auth_service.py"
    auth_service_path.write_text("# Dummy auth service\n", encoding="utf-8")

    # Mock sync result for validation_from_sync
    sync_result = {
        "results_by_language": {
            "python": {
                "success": True,
                "operations_completed": ["test", "verify"]
            }
        }
    }
    
    validation_state = validation_from_sync(
        sync_result,
        skip_tests=False,
        skip_verify=False,
        dry_run=False
    )
    
    print(f"Validation state: {json.dumps(validation_state, indent=2)}")
    print()

    # Write the manifest
    manifest_path = write_evidence_manifest(
        command="pdd sync",
        prompt_file=prompt_file,
        output_files=[auth_service_path],
        model="gpt-4o",
        cost_usd=0.01,
        temperature=0.0,
        project_root=workspace_dir,
        validation=validation_state,
        logs={"verify_results": str(auth_service_path)}
    )

    if manifest_path and manifest_path.exists():
        print(f"Manifest written to: {manifest_path}")
        manifest_content = json.loads(manifest_path.read_text(encoding="utf-8"))
        print("Manifest Content (partial):")
        # Print a few key fields to show it worked
        print(f"  Schema version: {manifest_content.get('schema_version')}")
        print(f"  Command: {manifest_content.get('run', {}).get('command')}")
        print(f"  Prompt path: {manifest_content.get('prompt', {}).get('path')}")
        print(f"  Validation unit_tests: {manifest_content.get('validation', {}).get('unit_tests')}")
        print(f"  Logs verify_results: {manifest_content.get('logs', {}).get('verify_results')}")
    else:
        print("Failed to write manifest.")
        sys.exit(1)

    print()
    print("Example completed successfully.")

if __name__ == "__main__":
    main()
