"""Cloud E2E: contract-rule test generation via ``pdd test`` (issue #821 / PR #1283)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

import pdd
from pdd import cli
from tests.contract_rule_cloud_e2e import (
    assert_contract_rule_merge_quality,
    real_llm_tests_enabled,
    requires_real_llm,
    setup_contract_rule_project,
)
from tests.test_cmd_test_main import _wait_for_cloud_credentials

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _set_pdd_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin PDD_PATH to the packaged prompts tree under this repository."""
    monkeypatch.setenv("PDD_PATH", str(Path(pdd.__file__).parent))


@pytest.mark.real
@pytest.mark.integration
@pytest.mark.e2e
@requires_real_llm
def test_pdd_test_merge_cloud_contract_rule_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    ``pdd test --manual --merge`` on a prompt with MUST / MUST NOT rules.

    Uses PDD Cloud (no ``--local``, no mocked ``generate_test``). Requires
    cloud auth and ``PDD_RUN_REAL_LLM_TESTS=1``.
    """
    if not _wait_for_cloud_credentials(max_retries=3, delay=1.0):
        pytest.skip(
            "Cloud credentials or JWT not available "
            "(run ``pdd auth login`` or set PDD_JWT_TOKEN)"
        )

    project = setup_contract_rule_project(tmp_path)
    existing_test = project / "tests" / "test_refund_policy.py"

    monkeypatch.chdir(project)
    monkeypatch.setenv("PDD_CLOUD_ONLY", "1")
    monkeypatch.delenv("PDD_FORCE_LOCAL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "--force",
            "--quiet",
            "test",
            "--manual",
            "refund_policy_python.prompt",
            "refund_policy.py",
            "--existing-tests",
            str(existing_test),
            "--merge",
            "--output",
            str(project / "tests" / "unused_output.py"),
        ],
        catch_exceptions=False,
    )

    if result.exit_code != 0:
        if "Account not approved" in result.output or "Insufficient credits" in result.output:
            pytest.skip(f"PDD Cloud not available for this account: {result.output[:500]}")
        pytest.fail(result.output)

    assert "Cloud Success" in result.output, (
        f"expected cloud execution (not local fallback); output:\n{result.output[:800]}"
    )

    merged = existing_test.read_text(encoding="utf-8")
    assert_contract_rule_merge_quality(merged)
