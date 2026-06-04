"""Unit tests for marketplace regeneration demo live helpers."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = REPO_ROOT / "examples" / "marketplace_compression_regeneration_demo"
sys.path.insert(0, str(DEMO_DIR))

from run_demo import (  # noqa: E402
    _evidence_basename_for_prompt,
    _filter_placeholder_pins,
    _fixture_marketplace_few_shot_metrics,
    _is_placeholder_pin,
    _live_marketplace_verified,
    _load_marketplace_catalog,
    _selected_have_marketplace_source,
)


def test_placeholder_pins_are_filtered() -> None:
    assert _is_placeholder_pin("slug/from/your/cloud")
    assert _filter_placeholder_pins(
        ["slug/from/your/cloud", "marketplace/ticket-classifier-bug"]
    ) == ["marketplace/ticket-classifier-bug"]


def test_evidence_basename_for_live_prompt() -> None:
    path = DEMO_DIR / "prompts" / "ticket_classifier_live_python.prompt"
    assert _evidence_basename_for_prompt(path) == "ticket_classifier_live"


def test_fixture_marketplace_few_shot_compresses() -> None:
    catalog = _load_marketplace_catalog()
    metrics = _fixture_marketplace_few_shot_metrics(catalog)
    assert metrics["uncompressed_chars"] > metrics["compressed_chars"]
    assert metrics["reduction_chars"] > 0


def test_selected_have_marketplace_source() -> None:
    assert _selected_have_marketplace_source([{"source": "marketplace", "module": "a"}])
    assert not _selected_have_marketplace_source([{"module": "auto-submitted"}])


def test_live_marketplace_verified_via_pin_match() -> None:
    catalog = _load_marketplace_catalog()
    selected = [{"module": "ticket-classifier-bug-severity-pattern-elu"}]
    pins = [
        "marketplace/ticket-classifier-bug",
        "ticket-classifier-bug-severity-pattern-elu",
    ]
    verified, reason = _live_marketplace_verified(
        selected,
        catalog=catalog,
        pin_modules=pins,
    )
    assert verified
    assert "pin" in reason
