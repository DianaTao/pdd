#!/usr/bin/env python3
"""Human-runnable demo: gate failure codes after a failed ``pdd sync --evidence``.

No API keys. Does not modify your working tree (uses a temp project copy).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from examples.checkup_gate_demo.manifests import write_demo_manifest  # noqa: E402
from pdd.evidence_store import sha256_file  # noqa: E402
from pdd.gate_main import run_gate_policy  # noqa: E402

DEMO_ROOT = Path(__file__).resolve().parent
EXPECTED_CODES = frozenset(
    {"stories_pass", "verify_not_available", "unit_tests_pass"}
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pdd-gate-failed-sync-") as temp_dir:
        project = Path(temp_dir)
        (project / "prompts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            DEMO_ROOT / "prompts" / "refund_python.prompt",
            project / "prompts" / "refund_python.prompt",
        )

        code_path = project / "src" / "refund.py"
        code_path.parent.mkdir(parents=True, exist_ok=True)
        code_path.write_text(
            "def refund(amount: float, original_charge: float | None = None) -> float:\n"
            "  if amount <= 0:\n"
            "    raise ValueError('amount must be positive')\n"
            "  if original_charge is not None and amount > original_charge:\n"
            "    raise ValueError('refund exceeds original charge')\n"
            "  return amount\n",
            encoding="utf-8",
        )

        manifest_path = project / ".pdd" / "evidence" / "devunits" / "refund.latest.json"
        write_demo_manifest(
            manifest_path,
            basename="refund",
            output_rel="src/refund.py",
            output_hash=sha256_file(code_path),
            validation={
                "detect_stories": "not_applicable",
                "unit_tests": "failed",
                "verify": "not_available",
            },
            cost_usd=0.8,
        )

        result = run_gate_policy(project, target="refund")
        payload = result.as_dict()

    print("Equivalent live CLI (from examples/checkup_gate_demo/ after failed sync):")
    print("  pdd checkup gate refund --json")
    print()
    print(json.dumps(payload, indent=2))

    if result.passed:
        print("Expected gate to fail on failed-sync-shaped manifest", file=sys.stderr)
        return 1

    codes = {failure.code for failure in result.failures}
    missing = EXPECTED_CODES - codes
    if missing:
        print(f"Missing failure codes: {sorted(missing)}", file=sys.stderr)
        return 1

    print()
    print("Gate failed as expected:")
    for failure in result.failures:
        if failure.code in EXPECTED_CODES:
            print(f"  - {failure.code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
