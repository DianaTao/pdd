"""Behavior contract for marketplace compression / sync demos."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "generated"))

from ticket_classifier import classify_ticket, format_ticket_json  # noqa: E402


def test_classify_bug_high() -> None:
    assert classify_ticket("The app crashes when I click Save.") == {
        "category": "bug",
        "severity": "high",
    }


def test_classify_feature_medium() -> None:
    assert classify_ticket("Please add dark mode to the dashboard.") == {
        "category": "feature_request",
        "severity": "medium",
    }


def test_classify_docs_low() -> None:
    assert classify_ticket("The README is missing install steps.") == {
        "category": "documentation",
        "severity": "low",
    }


def test_format_ticket_json_usability() -> None:
    assert format_ticket_json("Dashboard feels slow on mobile.") == (
        '{"category": "usability", "severity": "medium"}'
    )
