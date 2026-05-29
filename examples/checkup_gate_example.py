"""Offline walkthrough of ``pdd checkup gate`` policy scenarios (no LLM)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from pdd.evidence_manifest import validation_from_sync
from pdd.evidence_store import sha256_file
from pdd.gate_main import run_gate_policy

from examples.checkup_gate_demo.manifests import write_demo_manifest

FIXTURE_ROOT = Path(__file__).resolve().parent / "checkup_gate_demo"
PASSING_VALIDATION = {
    "detect_stories": "pass",
    "verify": "pass",
    "unit_tests": "pass",
}
GENERATE_ONLY_VALIDATION = {
    "detect_stories": "not_available",
    "unit_tests": "not_available",
    "verify": "not_available",
}


def _codes(result) -> list[str]:
    return [failure.code for failure in result.failures]


def _section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _run_scenario(
    title: str,
    *,
    setup,
    target: str | None = None,
    policy_path: Path | None = None,
    expect_passed: bool,
    expect_codes: set[str] | None = None,
    cli_hint: str,
) -> None:
    _section(title)
    print(f"CLI equivalent: {cli_hint}")
    with tempfile.TemporaryDirectory(prefix="pdd-gate-demo-") as temp_dir:
        project = Path(temp_dir)
        setup(project)
        result = run_gate_policy(
            project,
            target=target,
            policy_path=policy_path,
        )
        print(f"passed={result.passed} manifests_checked={result.manifests_checked}")
        if result.failures:
            for failure in result.failures:
                print(f"  - {failure.code}: {failure.message}")
                if failure.fix_command:
                    print(f"    fix: {failure.fix_command}")
        assert result.passed is expect_passed, (
            f"expected passed={expect_passed}, got {result.passed}, codes={_codes(result)}"
        )
        if expect_codes is not None:
            missing = expect_codes - set(_codes(result))
            assert not missing, f"missing expected codes: {missing}, got {_codes(result)}"
    print("OK")


def _write_minimal_refund_code(code_path: Path) -> Path:
    """Write minimal generated-style code for offline gate hash checks."""
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text(
        "def refund(amount: float, original_charge: float | None = None) -> float:\n"
        "    if amount <= 0:\n"
        "        raise ValueError('amount must be positive')\n"
        "    if original_charge is not None and amount > original_charge:\n"
        "        raise ValueError('refund exceeds original charge')\n"
        "    return amount\n",
        encoding="utf-8",
    )
    return code_path


def _copy_fixture_prompt(project: Path) -> Path:
    """Copy only the hand-crafted prompt into a temp project."""
    dest_prompt = project / "prompts" / "refund_python.prompt"
    dest_prompt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURE_ROOT / "prompts" / "refund_python.prompt", dest_prompt)
    return dest_prompt


def main() -> None:
    """Run gate scenarios and print CLI hints for live demos."""
    print("PDD checkup gate — offline demonstration")
    print(f"Fixture: {FIXTURE_ROOT}")

    _run_scenario(
        "1. No manifests (no_manifests)",
        setup=lambda _project: None,
        target=None,
        expect_passed=False,
        expect_codes={"no_manifests"},
        cli_hint="cd <empty-dir> && pdd checkup gate",
    )

    _run_scenario(
        "2. Generate-only validation (not_available)",
        setup=lambda project: (
            _copy_fixture_prompt(project),
            write_demo_manifest(
                project / ".pdd" / "evidence" / "devunits" / "refund.latest.json",
                basename="refund",
                output_rel="src/refund.py",
                output_hash=sha256_file(
                    _write_minimal_refund_code(project / "src" / "refund.py")
                ),
                validation=GENERATE_ONLY_VALIDATION,
            ),
        ),
        target="refund",
        expect_passed=False,
        expect_codes={
            "detect_stories_not_available",
            "unit_tests_not_available",
            "verify_not_available",
        },
        cli_hint="pdd generate … --evidence && pdd checkup gate refund --json",
    )

    _run_scenario(
        "3. Fresh manifest (pass)",
        setup=lambda project: (
            _copy_fixture_prompt(project),
            write_demo_manifest(
                project / ".pdd" / "evidence" / "devunits" / "refund.latest.json",
                basename="refund",
                output_rel="src/refund.py",
                output_hash=sha256_file(
                    _write_minimal_refund_code(project / "src" / "refund.py")
                ),
                validation=PASSING_VALIDATION,
            ),
        ),
        target="refund",
        expect_passed=True,
        expect_codes=set(),
        cli_hint=(
            "cd examples/checkup_gate_demo && "
            "pdd sync refund --evidence && "
            "pdd checkup contract check prompts/ && "
            "pdd checkup coverage prompts/ && "
            "pdd checkup gate refund --json"
        ),
    )

    _run_scenario(
        "4. Stale output hash (stale_output)",
        setup=lambda project: (
            _copy_fixture_prompt(project),
            _write_minimal_refund_code(project / "src" / "refund.py"),
            write_demo_manifest(
                project / ".pdd" / "evidence" / "devunits" / "refund.latest.json",
                basename="refund",
                output_rel="src/refund.py",
                output_hash="deadbeef",
                validation=PASSING_VALIDATION,
            ),
        ),
        target="refund",
        expect_passed=False,
        expect_codes={"stale_output"},
        cli_hint="edit src/refund.py after evidence, then pdd checkup gate refund --json",
    )

    def _skip_shaped_setup(project: Path) -> None:
        _copy_fixture_prompt(project)
        code = _write_minimal_refund_code(project / "src" / "refund.py")
        validation = validation_from_sync({}, skip_tests=True, skip_verify=True)
        validation["detect_stories"] = "passed"
        write_demo_manifest(
            project / ".pdd" / "evidence" / "devunits" / "refund.latest.json",
            basename="refund",
            output_rel="src/refund.py",
            output_hash=sha256_file(code),
            validation=validation,
        )

    _run_scenario(
        "5. Skip-shaped sync validation (default policy fails)",
        setup=_skip_shaped_setup,
        target="refund",
        expect_passed=False,
        expect_codes={"skipped_tests", "skipped_verify"},
        cli_hint="pdd sync --skip-tests --skip-verify --evidence; pdd checkup gate refund",
    )

    _run_scenario(
        "6. Permissive policy allows skip-shaped validation",
        setup=_skip_shaped_setup,
        target="refund",
        policy_path=FIXTURE_ROOT / ".pdd" / "policy-permissive.yml",
        expect_passed=True,
        expect_codes=set(),
        cli_hint=(
            "pdd checkup gate refund "
            "--policy examples/checkup_gate_demo/.pdd/policy-permissive.yml --json"
        ),
    )

    _section("Done")
    print("All offline scenarios passed.")
    print()
    print("Next: run the agent walkthrough prompt:")
    print(f"  less {FIXTURE_ROOT / 'agent.prompt'}")
    print("Or run the full CLI showcase:")
    print("  cd examples/checkup_gate_demo && ./run_demo.sh")


if __name__ == "__main__":
    main()
