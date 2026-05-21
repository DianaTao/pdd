"""Tests for pdd.evidence_manifest (deterministic — no LLM)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdd.evidence_manifest import (
    SCHEMA,
    EvidenceManifest,
    ManifestValidation,
    RuleEvidence,
    build_manifest,
    emit_manifest,
    validate_manifest,
)


def _contract_prompt(tmp_path: Path) -> Path:
    p = tmp_path / "foo.prompt"
    p.write_text(
        "<prompt>\nModule that validates amounts.\n</prompt>\n\n"
        "<contract_rules>\n"
        "R1 - Validate input\n"
        "When amount is negative, the module MUST raise ValueError.\n"
        "R2 - Return result\n"
        "When amount is valid, the module MUST return a float.\n"
        "</contract_rules>\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# EvidenceManifest unit tests
# ---------------------------------------------------------------------------


def test_build_manifest_schema(tmp_path: Path) -> None:
    p = _contract_prompt(tmp_path)
    manifest = build_manifest(p)
    assert manifest.schema == SCHEMA


def test_build_manifest_sha256(tmp_path: Path) -> None:
    p = _contract_prompt(tmp_path)
    manifest = build_manifest(p)
    assert len(manifest.prompt_sha256) == 64
    assert manifest.prompt_sha256 != ""


def test_build_manifest_rule_count(tmp_path: Path) -> None:
    p = _contract_prompt(tmp_path)
    manifest = build_manifest(p)
    assert manifest.rule_count == len(manifest.rules)


def test_build_manifest_no_llm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """build_manifest must never call any LLM."""
    called = []

    def _fake(*a, **kw):
        called.append(True)
        return {}

    monkeypatch.setattr("pdd.evidence_manifest.llm_invoke", _fake, raising=False)
    p = _contract_prompt(tmp_path)
    build_manifest(p)
    assert not called


def test_build_manifest_gap_flag(tmp_path: Path) -> None:
    """Rules with unchecked status are flagged as gaps; test-only rules are not."""
    p = _contract_prompt(tmp_path)
    manifest = build_manifest(p)
    # gap=True only when status is "unchecked" or story-only with no tests.
    # "test-only" rules have gap=False (they have test coverage, just no stories).
    for rule in manifest.rules:
        if rule.status == "unchecked":
            assert rule.gap is True
        elif rule.status in ("checked", "test-only", "waived"):
            assert rule.gap is False


def test_build_manifest_json_serialisable(tmp_path: Path) -> None:
    p = _contract_prompt(tmp_path)
    manifest = build_manifest(p)
    json.dumps(manifest.as_dict())  # must not raise


# ---------------------------------------------------------------------------
# emit_manifest
# ---------------------------------------------------------------------------


def test_emit_manifest_writes_file(tmp_path: Path) -> None:
    p = _contract_prompt(tmp_path)
    out = tmp_path / "reports" / "evidence.json"
    manifest = emit_manifest(p, output_path=out)
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == SCHEMA


def test_emit_manifest_no_output_returns_manifest(tmp_path: Path) -> None:
    p = _contract_prompt(tmp_path)
    manifest = emit_manifest(p)
    assert isinstance(manifest, EvidenceManifest)


# ---------------------------------------------------------------------------
# validate_manifest
# ---------------------------------------------------------------------------


def test_validate_manifest_valid(tmp_path: Path) -> None:
    p = _contract_prompt(tmp_path)
    out = tmp_path / "evidence.json"
    emit_manifest(p, output_path=out)
    val = validate_manifest(out)
    assert val.valid
    assert val.schema == SCHEMA
    assert val.errors == []


def test_validate_manifest_wrong_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({
            "schema": "wrong.schema.v1",
            "generated_at": "now",
            "prompt_path": "x",
            "prompt_sha256": "abc",
            "rule_count": 0,
            "rules": [],
        }),
        encoding="utf-8",
    )
    val = validate_manifest(bad)
    assert not val.valid
    assert any("schema mismatch" in e for e in val.errors)


def test_validate_manifest_missing_keys(tmp_path: Path) -> None:
    bad = tmp_path / "missing.json"
    bad.write_text(json.dumps({"schema": SCHEMA}), encoding="utf-8")
    val = validate_manifest(bad)
    assert not val.valid
    assert len(val.errors) >= 1


def test_validate_manifest_unreadable(tmp_path: Path) -> None:
    val = validate_manifest(tmp_path / "nonexistent.json")
    assert not val.valid


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


def test_evidence_emit_cli_smoke(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.evidence import evidence_emit

    p = _contract_prompt(tmp_path)
    runner = CliRunner()
    result = runner.invoke(evidence_emit, [str(p)])
    assert result.exit_code == 0


def test_evidence_emit_cli_json(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.evidence import evidence_emit

    p = _contract_prompt(tmp_path)
    runner = CliRunner()
    result = runner.invoke(evidence_emit, ["--json", str(p)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema"] == SCHEMA


def test_evidence_emit_cli_markdown(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.evidence import evidence_emit

    p = _contract_prompt(tmp_path)
    runner = CliRunner()
    result = runner.invoke(evidence_emit, ["--markdown", str(p)])
    assert result.exit_code == 0
    assert "Evidence report" in result.output


def test_evidence_validate_cli_valid(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.evidence import evidence_emit, evidence_validate

    p = _contract_prompt(tmp_path)
    out = tmp_path / "ev.json"
    runner = CliRunner()
    runner.invoke(evidence_emit, ["--output", str(out), str(p)])
    result = runner.invoke(evidence_validate, [str(out)])
    assert result.exit_code == 0


def test_evidence_validate_cli_invalid(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from pdd.commands.evidence import evidence_validate

    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(evidence_validate, [str(bad)])
    assert result.exit_code == 2
