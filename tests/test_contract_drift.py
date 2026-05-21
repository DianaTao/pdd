"""Tests for pdd.contract_drift (structural check is deterministic)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pdd.contract_drift import (
    FINDING_KIND_STRUCTURAL,
    DriftFinding,
    DriftResult,
    structural_drift,
)


def _prompt_with_must_not(tmp_path: Path, term: str = "cache_client") -> Path:
    p = tmp_path / "foo.prompt"
    p.write_text(
        "<prompt>\nModule that caches results.\n</prompt>\n\n"
        "<contract_rules>\n"
        f"R1 - No cache\n"
        f"When fetching data, the module MUST NOT call {term}.\n"
        "</contract_rules>\n",
        encoding="utf-8",
    )
    return p


def _code_with_term(tmp_path: Path, term: str = "cache_client") -> Path:
    p = tmp_path / "foo.py"
    p.write_text(
        f"def fetch():\n"
        f"    result = {term}.get('key')\n"
        f"    return result\n",
        encoding="utf-8",
    )
    return p


def _code_clean(tmp_path: Path) -> Path:
    p = tmp_path / "foo.py"
    p.write_text(
        "def fetch():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Structural drift
# ---------------------------------------------------------------------------


def test_structural_drift_finds_must_not_term(tmp_path: Path) -> None:
    prompt = _prompt_with_must_not(tmp_path)
    code = _code_with_term(tmp_path)
    findings = structural_drift(prompt, code)
    assert len(findings) >= 1
    assert findings[0].kind == FINDING_KIND_STRUCTURAL
    assert findings[0].rule_id == "R1"
    assert "cache_client" in findings[0].term


def test_structural_drift_clean_code(tmp_path: Path) -> None:
    prompt = _prompt_with_must_not(tmp_path)
    code = _code_clean(tmp_path)
    findings = structural_drift(prompt, code)
    assert findings == []


def test_structural_drift_no_contract_rules(tmp_path: Path) -> None:
    p = tmp_path / "plain.prompt"
    p.write_text("<prompt>\nDo something.\n</prompt>\n", encoding="utf-8")
    code = _code_clean(tmp_path)
    findings = structural_drift(p, code)
    assert findings == []


def test_structural_drift_skips_comment_lines(tmp_path: Path) -> None:
    prompt = _prompt_with_must_not(tmp_path, "cache_client")
    code = tmp_path / "foo.py"
    code.write_text(
        "# cache_client is documented here but not used\n"
        "def fetch():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    findings = structural_drift(prompt, code)
    assert findings == []


def test_structural_drift_finding_line_number(tmp_path: Path) -> None:
    prompt = _prompt_with_must_not(tmp_path)
    code = _code_with_term(tmp_path)
    findings = structural_drift(prompt, code)
    assert findings[0].line_number > 0


def test_structural_drift_json_serialisable(tmp_path: Path) -> None:
    prompt = _prompt_with_must_not(tmp_path)
    code = _code_with_term(tmp_path)
    findings = structural_drift(prompt, code)
    json.dumps([f.as_dict() for f in findings])  # must not raise


def test_drift_result_has_drift(tmp_path: Path) -> None:
    result = DriftResult(
        prompt_path="p.prompt",
        code_path="p.py",
        structural_findings=[
            DriftFinding(kind=FINDING_KIND_STRUCTURAL, rule_id="R1", message="drift")
        ],
    )
    assert result.has_drift is True
    assert result.finding_count == 1


def test_drift_result_no_drift() -> None:
    result = DriftResult(prompt_path="p.prompt", code_path="p.py")
    assert result.has_drift is False
    assert result.finding_count == 0


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


def test_contracts_drift_cli_no_drift(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.contracts import contracts_drift

    prompt = _prompt_with_must_not(tmp_path)
    code = _code_clean(tmp_path)
    runner = CliRunner()
    result = runner.invoke(contracts_drift, [str(prompt), str(code)])
    assert result.exit_code == 0


def test_contracts_drift_cli_with_drift(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.contracts import contracts_drift

    prompt = _prompt_with_must_not(tmp_path)
    code = _code_with_term(tmp_path)
    runner = CliRunner()
    # default: not strict → exit 0 even with findings
    result = runner.invoke(contracts_drift, [str(prompt), str(code)])
    assert result.exit_code == 0


def test_contracts_drift_cli_strict(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.contracts import contracts_drift

    prompt = _prompt_with_must_not(tmp_path)
    code = _code_with_term(tmp_path)
    runner = CliRunner()
    result = runner.invoke(contracts_drift, ["--strict", str(prompt), str(code)])
    assert result.exit_code == 1


def test_contracts_drift_cli_json(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.contracts import contracts_drift

    prompt = _prompt_with_must_not(tmp_path)
    code = _code_clean(tmp_path)
    runner = CliRunner()
    result = runner.invoke(contracts_drift, ["--json", str(prompt), str(code)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "structural_findings" in data
    assert "has_drift" in data
