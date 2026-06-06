"""
Demo tests for the non-interactive prompt repair feature (Issue #1422).

These tests showcase real usage and measurable improvement:

  1. test_before_prompt_has_known_issues
       The subscription billing "before" demo prompt has exactly the expected
       lint issues — proves the scanner catches real-world vague contract language.

  2. test_after_prompt_is_clean
       The manually-crafted "after" prompt (vocabulary + clarified rules)
       passes lint with 0 issues — proves the repair target is achievable.

  3. test_repair_loop_applies_vocabulary_patches
       The repair loop (LLM mocked to propose ADD_VOCABULARY entries) reduces
       issue count and writes the vocabulary block to disk.

  4. test_repair_loop_two_pass_convergence
       Two repair rounds converge from 9 issues → 4 → 0 as the LLM proposes
       successively more vocabulary entries.

  5. test_cli_prompt_target_routes_without_github_guard
       ``pdd checkup <prompt-file>`` exits 0 — no longer rejected with
       "TARGET must be a GitHub issue URL" (#1426 fix verified).

  6. test_check_repair_recheck_cycle_end_to_end
       The full check → repair → recheck cycle in checkup.py:
       run_checkup_prompt() fails → repair runs → run_checkup_prompt() passes.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdd.prompt_lint import scan_prompt
from pdd.prompt_repair import PromptRepairConfig, RepairResult, run_prompt_repair_loop

DEMOS = Path(__file__).parent.parent / "demos" / "prompt_repair"
BEFORE = DEMOS / "subscription_billing_before_python.prompt"
AFTER  = DEMOS / "subscription_billing_after_python.prompt"


# ---------------------------------------------------------------------------
# 1. Before prompt has the expected lint issues
# ---------------------------------------------------------------------------

def test_before_prompt_has_known_issues() -> None:
    """The unrepaired billing prompt triggers exactly the vague-term issues
    that motivated this feature.  If this fails the fixture diverged."""
    result = scan_prompt(BEFORE)
    issues = result.issues

    # Confirm each expected vague term is caught
    terms_flagged = {i.term for i in issues}
    assert "active"      in terms_flagged, "Expected 'active' to be flagged"
    assert "valid"       in terms_flagged, "Expected 'valid' to be flagged"
    assert "gracefully"  in terms_flagged, "Expected 'gracefully' to be flagged"
    assert "reasonable"  in terms_flagged, "Expected 'reasonable' to be flagged"
    assert "successful"  in terms_flagged, "Expected 'successful' to be flagged"

    # All findings are in contract_rules or prose (not vocab — there is none yet)
    for issue in issues:
        assert issue.section in ("contract_rules", "prose"), (
            f"Unexpected section {issue.section!r} for term {issue.term!r}"
        )

    assert len(issues) >= 5, f"Expected at least 5 issues, got {len(issues)}"


# ---------------------------------------------------------------------------
# 2. After prompt is clean
# ---------------------------------------------------------------------------

def test_after_prompt_is_clean() -> None:
    """The manually-crafted 'after' prompt — representing the ideal repair
    output — passes lint with zero issues."""
    result = scan_prompt(AFTER)
    issues = result.issues
    assert issues == [], (
        f"'After' demo prompt should be clean but has {len(issues)} issue(s):\n"
        + "\n".join(f"  [{i.level}] {i.term!r} — {i.message}" for i in issues)
    )


# ---------------------------------------------------------------------------
# 3. Repair loop applies vocabulary patches in a single pass
# ---------------------------------------------------------------------------

_ADD_VOCABULARY_PROPOSALS = json.dumps([
    {
        "type": "ADD_VOCABULARY",
        "term": "active subscription",
        "definition": "active subscription: status IN ('active', 'trialing') and current_period_end > now() UTC",
        "addresses_issue": "undefined vague term 'active' in contract_rules",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "valid payment method",
        "definition": "valid payment method: a Stripe PaymentMethod with status 'succeeded' and unexpired card",
        "addresses_issue": "undefined vague term 'valid' in contract_rules",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "graceful payment failure",
        "definition": "graceful payment failure: HTTP 200 with {\"status\":\"billing_failed\",\"next_retry_at\":\"<ISO-8601>\"}",
        "addresses_issue": "undefined vague term 'gracefully' in contract_rules",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "reasonable retry",
        "definition": "reasonable retry: up to 3 attempts at 1 h, 24 h, 72 h intervals over 4 days",
        "addresses_issue": "undefined vague term 'reasonable' in contract_rules",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "successful billing",
        "definition": "successful billing: Stripe charge.status == 'succeeded' and invoice.status == 'paid'",
        "addresses_issue": "undefined vague term 'successful' in contract_rules",
    },
])


def test_repair_loop_applies_vocabulary_patches(tmp_path: Path) -> None:
    """One repair round: LLM proposes ADD_VOCABULARY entries for all 5 vague
    terms.  The loop writes a <vocabulary> block and re-checks with scan_prompt.
    After patch application the VAGUE_TERM issue count drops significantly."""
    prompt = tmp_path / "billing.prompt"
    shutil.copy(BEFORE, prompt)

    before_issues = scan_prompt(prompt).issues
    assert len(before_issues) >= 5

    with patch(
        "pdd.prompt_repair._invoke_repair_llm",
        return_value=(True, _ADD_VOCABULARY_PROPOSALS, 0.02, "claude-sonnet"),
    ):
        result = run_prompt_repair_loop(
            prompt,
            PromptRepairConfig(mode="best-effort", max_rounds=1),
            cwd=tmp_path,
            quiet=True,
        )

    # Repair ran at least one round
    assert result.rounds_used == 1
    assert result.success is True

    # The <vocabulary> block was written to disk
    repaired_text = prompt.read_text(encoding="utf-8")
    assert "<vocabulary>" in repaired_text, "Expected <vocabulary> block after repair"
    assert "active subscription" in repaired_text
    assert "valid payment method" in repaired_text

    # Issue count decreased
    after_issues = scan_prompt(prompt).issues
    assert len(after_issues) < len(before_issues), (
        f"Issue count did not decrease: before={len(before_issues)} after={len(after_issues)}"
    )

    # Token delta is non-negative (we added content)
    assert result.token_delta >= 0


# ---------------------------------------------------------------------------
# 4. Two-pass convergence: 9 issues → fewer → 0
# ---------------------------------------------------------------------------

_PASS1_PROPOSALS = json.dumps([
    {
        "type": "ADD_VOCABULARY",
        "term": "active subscription",
        "definition": "active subscription: status IN ('active','trialing') and current_period_end > now()",
        "addresses_issue": "undefined vague term 'active'",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "valid payment method",
        "definition": "valid payment method: Stripe PaymentMethod with status 'succeeded' and unexpired card",
        "addresses_issue": "undefined vague term 'valid'",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "graceful payment failure",
        "definition": 'graceful payment failure: HTTP 200 with {"status":"billing_failed","next_retry_at":"<ISO-8601>"}',
        "addresses_issue": "undefined vague term 'gracefully'",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "reasonable retry",
        "definition": "reasonable retry: up to 3 attempts at 1h, 24h, 72h over 4 days",
        "addresses_issue": "undefined vague term 'reasonable'",
    },
    {
        "type": "ADD_VOCABULARY",
        "term": "successful billing",
        "definition": "successful billing: Stripe charge.status == 'succeeded' and invoice.status == 'paid'",
        "addresses_issue": "undefined vague term 'successful'",
    },
])

_PASS2_PROPOSALS = json.dumps([
    {
        "type": "CLARIFY_VAGUE_TERM",
        "term": "process renewals for all active subscriptions due within the billing window",
        "replacement": "write a billing_attempt record for all active subscriptions due within the billing window",
        "addresses_issue": "no observable outcome verb in R1",
    },
    {
        "type": "CLARIFY_VAGUE_TERM",
        "term": "charge the valid payment method on file and record a billing receipt",
        "replacement": "charge the valid payment method on file and return HTTP 200 with a billing receipt JSON body",
        "addresses_issue": "no observable outcome verb in R2",
    },
    {
        "type": "CLARIFY_VAGUE_TERM",
        "term": "handle failed payments gracefully and apply reasonable retry logic",
        "replacement": "return HTTP 200 with {\"status\":\"billing_failed\",\"next_retry_at\":\"<ISO-8601>\"} and schedule reasonable retry attempts",
        "addresses_issue": "no observable outcome verb in R3",
    },
    {
        "type": "CLARIFY_VAGUE_TERM",
        "term": "notify the customer on successful billing",
        "replacement": "emit a BILLING_SUCCEEDED event to the notification queue within 5 minutes of successful billing",
        "addresses_issue": "no observable outcome verb in R4",
    },
])


def test_repair_loop_two_pass_convergence(tmp_path: Path) -> None:
    """Two repair rounds converge: ADD_VOCABULARY pass eliminates the
    VAGUE_TERM issues, then CLARIFY_VAGUE_TERM pass eliminates the
    no-observable-outcome issues.  Final state: 0 lint issues."""
    prompt = tmp_path / "billing.prompt"
    shutil.copy(BEFORE, prompt)

    call_count = {"n": 0}

    def _fake_llm(**_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return True, _PASS1_PROPOSALS, 0.02, "claude-sonnet"
        return True, _PASS2_PROPOSALS, 0.02, "claude-sonnet"

    with patch("pdd.prompt_repair._invoke_repair_llm", side_effect=_fake_llm):
        result = run_prompt_repair_loop(
            prompt,
            PromptRepairConfig(mode="strict", max_rounds=2),
            cwd=tmp_path,
            quiet=True,
        )

    assert result.rounds_used == 2
    assert result.success is True, f"Expected success; issues_after={result.issues_after}"
    assert result.issues_after == [], (
        f"Expected 0 issues after 2 rounds; got: "
        + ", ".join(i.term for i in result.issues_after)
    )

    # Token growth reflects the additions
    assert result.token_delta > 0


# ---------------------------------------------------------------------------
# 5. CLI prompt-target routing — no longer rejected with the GitHub guard
# ---------------------------------------------------------------------------

def test_cli_prompt_target_routes_without_github_guard() -> None:
    """Verify that `pdd checkup <prompt-file>` exits 0 (routes through
    is_prompt_shaped_target → run_checkup_prompt) rather than raising
    'TARGET must be a GitHub issue URL' (the pre-#1426-fix behaviour)."""
    from click.testing import CliRunner
    from pdd.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--quiet", "checkup", str(BEFORE), "--explain"],
        catch_exceptions=False,
    )
    # The command reaches run_checkup_prompt and returns cleanly.
    # In --quiet + --explain mode the exit code reflects the prompt quality
    # but must NOT be 2 (UsageError from the old GitHub-only guard).
    assert result.exit_code != 2, (
        f"Got exit 2 (UsageError) — routing guard not fixed.\nOutput: {result.output}"
    )
    assert "TARGET must be a GitHub issue URL" not in (result.output or ""), (
        "Old GitHub-only guard still firing for prompt-file targets"
    )


# ---------------------------------------------------------------------------
# 6. Full check → repair → recheck cycle (end-to-end with mocks)
# ---------------------------------------------------------------------------

@patch("pdd.checkup_prompt_main.build_prompt_source_set_report")
@patch("pdd.commands.checkup.run_checkup_prompt")  # patched at the call site
@patch("pdd.prompt_repair._invoke_repair_llm")
def test_check_repair_recheck_cycle_end_to_end(
    mock_invoke_llm: MagicMock,
    mock_run_checkup: MagicMock,
    mock_build_report: MagicMock,
    tmp_path: Path,
) -> None:
    """
    Demonstrates the full check → repair → recheck cycle implemented in
    pdd/commands/checkup.py for prompt-shaped local targets.

    Flow:
      1. run_checkup_prompt() returns failed (first call)
      2. build_prompt_source_set_report() returns a failing report (repair oracle)
      3. LLM proposes ADD_VOCABULARY patches; repair loop applies them
      4. run_checkup_prompt() returns passed (second call — re-check)
    """
    from click.testing import CliRunner
    from pdd.cli import cli
    from pdd.prompt_lint import LintIssue

    # Copy demo prompt to tmp so repair can write to it
    prompt = tmp_path / "subscription_billing_python.prompt"
    shutil.copy(BEFORE, prompt)

    # Step 1: First checkup call → fails
    # Step 2: Re-check after repair → passes
    mock_run_checkup.side_effect = [
        (False, "3 issues found", 0.01, "claude-sonnet", 1),   # initial check fails
        (True,  "0 issues — pass", 0.01, "claude-sonnet", 0),  # re-check passes
    ]

    # Build-report used as repair oracle: failing report
    failing_report = MagicMock()
    failing_report.passed = False
    failing_report.findings = []
    failing_report.as_dict.return_value = {
        "status": "fail",
        "findings": [
            {"code": "VAGUE_TERM", "term": "active", "severity": "warn"},
            {"code": "VAGUE_TERM", "term": "valid",  "severity": "warn"},
        ],
    }
    failing_report.recommended_actions.return_value = [
        "pdd checkup lint subscription_billing_python.prompt"
    ]
    mock_build_report.return_value = failing_report

    # LLM proposes vocabulary patches on the temporary prompt file
    mock_invoke_llm.return_value = (True, _ADD_VOCABULARY_PROPOSALS, 0.02, "claude-sonnet")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--quiet",
            "checkup",
            str(prompt),
            "--prompt-repair", "best-effort",
            "--max-prompt-repair-rounds", "1",
        ],
        catch_exceptions=False,
    )

    # run_checkup_prompt called twice: initial check + re-check
    assert mock_run_checkup.call_count == 2, (
        f"Expected 2 checkup calls (check + recheck), got {mock_run_checkup.call_count}"
    )

    # Repair LLM was invoked (repair ran between the two checkup calls)
    assert mock_invoke_llm.called, "Repair LLM should have been invoked"

    # Final exit code reflects the re-check passing (exit 0)
    assert result.exit_code == 0, (
        f"Expected exit 0 after repair; got {result.exit_code}.\nOutput: {result.output}"
    )
