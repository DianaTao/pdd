"""Tests for ``pdd drift`` regeneration stability."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pdd import cli
from pdd.drift_main import run_drift
from pdd.evidence_store import sha256_file


def _write_fixture(project: Path) -> tuple[Path, Path]:
    prompt = project / "prompts" / "refund_payment_python.prompt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("<prompt>\nRefund module.\n</prompt>\n", encoding="utf-8")
    code = project / "pdd" / "refund_payment.py"
    code.parent.mkdir(parents=True)
    code.write_text(
        "def refund_payment(amount: int) -> int:\n    return amount\n",
        encoding="utf-8",
    )
    return prompt, code


def test_drift_dry_run_stable(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    report = run_drift("refund_payment", tmp_path, runs=3, dry_run=True)
    assert report.status == "stable"
    assert report.public_api_unchanged
    assert len(report.snapshots) == 3


def test_drift_detects_api_change(tmp_path: Path) -> None:
    from pdd.drift_main import RunSnapshot, _public_api

    _prompt, code = _write_fixture(tmp_path)
    first_api = _public_api(code)
    code.write_text("class RefundService:\n    pass\n", encoding="utf-8")
    second_api = _public_api(code)
    assert first_api != second_api

    snapshots = [
        RunSnapshot(1, "a", first_api, True, True, True, True),
        RunSnapshot(2, "b", second_api, True, True, True, True),
    ]
    apis = [snap.public_api for snap in snapshots]
    assert not all(api == apis[0] for api in apis)


def test_drift_from_evidence_manifest(tmp_path: Path) -> None:
    prompt, code = _write_fixture(tmp_path)
    manifest = tmp_path / ".pdd" / "evidence" / "devunits" / "refund_payment.latest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "prompt": {"path": str(prompt.relative_to(tmp_path))},
                "outputs": [
                    {
                        "path": str(code.relative_to(tmp_path)),
                        "sha256": sha256_file(code),
                    }
                ],
                "validation": {"unit_tests": "pass"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = run_drift(
        "refund_payment",
        tmp_path,
        runs=1,
        dry_run=True,
        from_evidence=manifest,
    )
    assert report.code_path.endswith("refund_payment.py")


def test_drift_json_payload(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    report = run_drift("refund_payment", tmp_path, runs=2, dry_run=True)
    payload = report.as_dict()
    assert payload["status"] == "stable"
    assert payload["runs"] == 2
    assert len(payload["snapshots"]) == 2


def test_drift_cli_dry_run_multi_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``pdd checkup drift <devunit> --dry-run --runs 3`` exits 0 when stable."""
    _write_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli.cli,
        ["--quiet", "checkup", "drift", "refund_payment", "--dry-run", "--runs", "3"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_drift_cli_from_evidence_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``pdd checkup drift --from-evidence ... --json`` emits stable JSON payload."""
    prompt, code = _write_fixture(tmp_path)
    manifest = tmp_path / ".pdd" / "evidence" / "devunits" / "refund_payment.latest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "prompt": {"path": str(prompt.relative_to(tmp_path))},
                "outputs": [
                    {"path": str(code.relative_to(tmp_path)), "sha256": sha256_file(code)}
                ],
                "validation": {"unit_tests": "pass"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli.cli,
        [
            "--quiet",
            "checkup",
            "drift",
            "refund_payment",
            "--dry-run",
            "--from-evidence",
            str(manifest),
            "--json",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "stable"
    assert payload["devunit"] == "refund_payment"
