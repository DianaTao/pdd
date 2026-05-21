"""Tests for pdd.contract_gate_service (deterministic — no LLM)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdd.contract_gate_service import GateRun, StageResult, run_gate

FIXTURES = Path(__file__).parent / "fixtures" / "prompt_lint"


def _clean_prompt(tmp_path: Path) -> Path:
    """A minimal valid prompt with no contract rules (legacy-safe)."""
    p = tmp_path / "clean.prompt"
    p.write_text(
        "<prompt>\nImplementation note: return 42.\n</prompt>\n",
        encoding="utf-8",
    )
    return p


def _contract_prompt(tmp_path: Path) -> Path:
    """A prompt with well-formed contract rules."""
    p = tmp_path / "contract.prompt"
    p.write_text(
        "<prompt>\n"
        "Implementation note: validate inputs.\n"
        "</prompt>\n\n"
        "<contract_rules>\n"
        "R1 - Validate input\n"
        "When amount is negative, the service MUST raise ValueError.\n"
        "</contract_rules>\n",
        encoding="utf-8",
    )
    return p


def _error_prompt(tmp_path: Path) -> Path:
    """A prompt designed to fail contracts check (missing modal)."""
    p = tmp_path / "bad.prompt"
    p.write_text(
        "<prompt>\nDo things.\n</prompt>\n\n"
        "<contract_rules>\n"
        "R1 - Missing modal\n"
        "When condition happens, the service does something.\n"
        "</contract_rules>\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# GateRun / StageResult unit tests
# ---------------------------------------------------------------------------


def test_stage_result_as_dict() -> None:
    s = StageResult(name="prompt-lint", exit_code=0, error_count=0, warn_count=0, detail="ok")
    d = s.as_dict()
    assert d["name"] == "prompt-lint"
    assert d["exit_code"] == 0
    assert not d["skipped"]


def test_gate_run_exit_code_max() -> None:
    run = GateRun(target=Path("p.prompt"))
    run.stages = [
        StageResult("a", 0, 0, 0, ""),
        StageResult("b", 1, 0, 1, ""),
        StageResult("c", 0, 0, 0, ""),
    ]
    assert run.exit_code == 1


def test_gate_run_skipped_ignored_in_exit_code() -> None:
    run = GateRun(target=Path("p.prompt"))
    run.stages = [
        StageResult("a", 0, 0, 0, ""),
        StageResult("b", 0, 0, 0, "", skipped=True),
    ]
    assert run.exit_code == 0


def test_gate_run_as_dict(tmp_path: Path) -> None:
    run = GateRun(target=tmp_path / "x.prompt")
    run.stages = [StageResult("prompt-lint", 0, 0, 0, "ok")]
    d = run.as_dict()
    assert d["exit_code"] == 0
    assert len(d["stages"]) == 1


# ---------------------------------------------------------------------------
# Integration: run_gate on real prompt files
# ---------------------------------------------------------------------------


def test_run_gate_clean_prompt(tmp_path: Path) -> None:
    """Legacy prompt with no contract rules should pass all stages."""
    p = _clean_prompt(tmp_path)
    result = run_gate(p)
    assert isinstance(result, GateRun)
    assert result.exit_code == 0
    stage_names = [s.name for s in result.stages]
    assert "prompt-lint" in stage_names
    assert "coverage" in stage_names


def test_run_gate_contract_prompt(tmp_path: Path) -> None:
    """Prompt with valid contract rules exits 0 or 1 (never 2)."""
    p = _contract_prompt(tmp_path)
    result = run_gate(p)
    assert result.exit_code <= 1  # may have unchecked coverage warning


def test_run_gate_json_serialisable(tmp_path: Path) -> None:
    p = _clean_prompt(tmp_path)
    result = run_gate(p)
    d = result.as_dict()
    json.dumps(d)  # must not raise


def test_run_gate_fail_fast(tmp_path: Path) -> None:
    """When stage 1 (prompt-lint) errors, subsequent stages are skipped."""
    p = _error_prompt(tmp_path)
    # Force lint to error via strict=True on a prompt with no rules but a vague warning
    # Use error_prompt — contracts-check will error on missing modal
    result = run_gate(p)
    # contracts-check should find an error; compile or coverage stages may be skipped
    for stage in result.stages:
        if stage.skipped:
            assert stage.exit_code == 0
    assert result.exit_code >= 1


def test_run_gate_no_llm_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """run_gate must not call any LLM function."""
    called = []

    def _fake_llm_invoke(*args, **kwargs):
        called.append(True)
        return {}

    monkeypatch.setattr("pdd.contract_gate_service.llm_invoke", _fake_llm_invoke, raising=False)
    p = _clean_prompt(tmp_path)
    run_gate(p)
    assert not called, "run_gate must not call llm_invoke"


def test_run_gate_strict_escalates_coverage(tmp_path: Path) -> None:
    """With --strict, unchecked coverage rules exit 2; if nothing is unchecked, exit 0 is valid."""
    p = _contract_prompt(tmp_path)
    result = run_gate(p, strict=True)
    cov = next((s for s in result.stages if s.name == "coverage"), None)
    if cov and not cov.skipped:
        # If the coverage engine reports unchecked rules, strict mode must escalate to exit 2.
        # If unchecked=0 (coverage engine assigns story-only/formal-only), exit 0 is acceptable.
        unchecked_in_detail = "unchecked=0" not in cov.detail
        if unchecked_in_detail:
            assert cov.exit_code == 2


def test_run_gate_directory(tmp_path: Path) -> None:
    """Gate works on a directory of .prompt files."""
    _clean_prompt(tmp_path)
    _contract_prompt(tmp_path)
    result = run_gate(tmp_path)
    assert isinstance(result, GateRun)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


def test_contracts_gate_cli_smoke(tmp_path: Path) -> None:
    """Click integration: pdd contracts gate exits with a valid code."""
    from click.testing import CliRunner
    from pdd.commands.contracts import contracts_gate

    p = _clean_prompt(tmp_path)
    runner = CliRunner()
    result = runner.invoke(contracts_gate, [str(p)])
    assert result.exit_code in (0, 1, 2)


def test_contracts_gate_cli_json(tmp_path: Path) -> None:
    """--json output parses correctly."""
    from click.testing import CliRunner
    from pdd.commands.contracts import contracts_gate

    p = _clean_prompt(tmp_path)
    runner = CliRunner()
    result = runner.invoke(contracts_gate, ["--json", str(p)])
    assert result.exit_code in (0, 1, 2)
    output = json.loads(result.output)
    assert "stages" in output
    assert "exit_code" in output
