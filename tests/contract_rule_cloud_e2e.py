"""Shared helpers for contract-rule cloud E2E tests (issue #821)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "test_generation"

RUN_ALL_TESTS_ENABLED = os.getenv("PDD_RUN_ALL_TESTS") == "1"


def real_llm_tests_enabled() -> bool:
    """Match repo gate for tests that bill real LLM / cloud usage."""
    return bool(os.getenv("PDD_RUN_REAL_LLM_TESTS") or RUN_ALL_TESTS_ENABLED)


requires_real_llm = pytest.mark.skipif(
    not real_llm_tests_enabled(),
    reason=(
        "Real cloud LLM tests require PDD_RUN_REAL_LLM_TESTS=1 "
        "or PDD_RUN_ALL_TESTS=1"
    ),
)


def setup_contract_rule_project(tmp_path: Path) -> Path:
    """
    Build an isolated mini-project with context/test.prompt and R1/R2 fixtures.

    Returns the project root (caller should chdir here for relative CLI paths).
    """
    project = tmp_path / "contract_rule_project"
    project.mkdir()
    context_dir = project / "context"
    context_dir.mkdir()
    shutil.copy(REPO_ROOT / "context" / "test.prompt", context_dir / "test.prompt")

    shutil.copy(
        FIXTURE_DIR / "refund_policy_python.prompt",
        project / "refund_policy_python.prompt",
    )
    shutil.copy(FIXTURE_DIR / "refund_policy.py", project / "refund_policy.py")

    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_refund_policy.py").write_text(
        "def test_existing_accumulated_refund_case():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    return project


def assert_contract_rule_merge_quality(merged: str) -> None:
    """Flexible assertions for real LLM output (wording varies by model)."""
    assert "test_existing_accumulated_refund_case" in merged
    assert merged.count("def test_") >= 2, (
        "merge should append at least one new test function"
    )
    markers = (
        "r1",
        "r2",
        "must not",
        "refund",
        "validate_refund",
        "approved",
        "rejected",
    )
    lower = merged.lower()
    assert any(marker in lower for marker in markers), (
        "expected contract-rule or refund-related content in merged tests"
    )
