
import os
from pathlib import Path
from pdd.gate_main import _check_validation_flags
from pdd.gate_policy import GatePolicy, GateLimits

# Mock ManifestView and validation data
class MockManifestView:
    def __init__(self, validation, basename="test_manifest"):
        self.validation = validation
        self.basename = basename
        self.path = Path("test_manifest.json")
        self.prompt_path = None

def test_repro(tmp_path):
    # Repro with a manifest containing verify: skipped, unit_tests: skipped
    validation = {
        "verify": "skipped",
        "unit_tests": "skipped",
        "detect_stories": "pass"
    }
    manifest = MockManifestView(validation)

    policy_file = tmp_path / "policy.yml"
    policy_file.write_text(
        "allow:\n  skipped_verify: true\n  skipped_tests: true\n",
        encoding="utf-8",
    )
    from pdd.gate_policy import load_policy
    policy = load_policy(policy_file)

    failures = _check_validation_flags(manifest, policy)
    
    print(f"Policy allow skipped_verify: {policy.allows('skipped_verify')}")
    print(f"Policy require verify_pass: {policy.requires('verify_pass')}")
    print(f"Manifest validation: {manifest.validation}")
    print(f"Failures: {[f.code for f in failures]}")
    if failures:
        print("Reproduction successful: Gate failed despite allow.skipped_*=true")
    else:
        print("Reproduction failed: Gate passed as expected")

if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        test_repro(Path(tmpdir))
