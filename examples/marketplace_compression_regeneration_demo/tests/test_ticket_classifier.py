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



import sys
from pathlib import Path

# Add project root to sys.path to ensure local code is prioritized
# This allows testing local changes without installing the package
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

"""Behavioral tests for the ticket_classifier module."""

# NOTE: The duplicate `from __future__ import annotations` that previously
# appeared here has been removed. A future import is only legal at the very
# top of a module (already present at line 3); a second occurrence mid-file
# raises SyntaxError at collection time.

import json
import sys
from pathlib import Path

import pytest

# The module under test lives in the sibling `generated/` directory.
_HERE = Path(__file__).resolve().parent

from ticket_classifier import classify_ticket, format_ticket_json  # noqa: E402


VALID_CATEGORIES = {"bug", "feature_request", "documentation", "usability", "other"}
VALID_SEVERITIES = {"low", "medium", "high"}


# --- classify_ticket: keyword-driven categories ---------------------------

def test_classify_bug_from_crash():
    assert classify_ticket("The app crashes when I click Save.") == {
        "category": "bug",
        "severity": "high",
    }


def test_classify_bug_from_error():
    assert classify_ticket("I get an Error 500 on submit.") == {
        "category": "bug",
        "severity": "high",
    }


def test_classify_feature_from_add():
    assert classify_ticket("Add a dark mode toggle.") == {
        "category": "feature_request",
        "severity": "medium",
    }


def test_classify_feature_from_please():
    assert classify_ticket("Please support CSV export.") == {
        "category": "feature_request",
        "severity": "medium",
    }


def test_classify_documentation_from_readme():
    assert classify_ticket("The README is missing install steps.") == {
        "category": "documentation",
        "severity": "low",
    }


def test_classify_documentation_from_docs():
    assert classify_ticket("The docs are out of date.") == {
        "category": "documentation",
        "severity": "low",
    }


def test_classify_usability_from_slow():
    assert classify_ticket("Dashboard feels slow.") == {
        "category": "usability",
        "severity": "medium",
    }


def test_classify_usability_from_mobile():
    assert classify_ticket("Layout breaks on mobile.") == {
        "category": "usability",
        "severity": "medium",
    }


def test_classify_other_default():
    assert classify_ticket("Hello there, just saying hi.") == {
        "category": "other",
        "severity": "low",
    }


def test_classify_empty_string_is_other():
    assert classify_ticket("") == {"category": "other", "severity": "low"}


# --- classify_ticket: case-insensitivity ----------------------------------

def test_classify_is_case_insensitive():
    assert classify_ticket("APP CRASHED HARD") == classify_ticket("app crashed hard")
    assert classify_ticket("APP CRASHED HARD")["category"] == "bug"


# --- classify_ticket: precedence ordering ---------------------------------

def test_bug_takes_precedence_over_feature():
    # Contains both "crash" (bug) and "please add" (feature); bug wins.
    assert classify_ticket("Please add a fix, it crashes.")["category"] == "bug"


def test_feature_takes_precedence_over_documentation():
    # Contains both "add" (feature) and "docs" (documentation); feature wins.
    result = classify_ticket("Please add docs section.")
    assert result["category"] == "feature_request"


def test_documentation_takes_precedence_over_usability():
    # Contains both "readme" (docs) and "slow" (usability); docs wins.
    result = classify_ticket("The README loads slow.")
    assert result["category"] == "documentation"


# --- classify_ticket: structural invariants -------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "The app crashes",
        "Please add a feature",
        "Update the README",
        "It's slow on mobile",
        "Totally unrelated message",
        "",
        "ERROR error ERROR",
    ],
)
def test_classify_returns_only_expected_keys_and_values(text):
    result = classify_ticket(text)
    assert set(result.keys()) == {"category", "severity"}
    assert result["category"] in VALID_CATEGORIES
    assert result["severity"] in VALID_SEVERITIES


def test_classify_is_deterministic():
    text = "Please add dark mode."
    assert classify_ticket(text) == classify_ticket(text)


# --- format_ticket_json ----------------------------------------------------

def test_format_ticket_json_usability():
    assert format_ticket_json("Dashboard feels slow on mobile.") == (
        '{"category": "usability", "severity": "medium"}'
    )


def test_format_ticket_json_is_valid_json():
    parsed = json.loads(format_ticket_json("The app crashes."))
    assert parsed == {"category": "bug", "severity": "high"}


def test_format_ticket_json_keys_sorted():
    out = format_ticket_json("Add dark mode")
    # 'category' must appear before 'severity' due to sort_keys=True.
    assert out.index('"category"') < out.index('"severity"')


def test_format_ticket_json_matches_classify_ticket():
    text = "Please add an export button."
    assert json.loads(format_ticket_json(text)) == classify_ticket(text)


def test_format_ticket_json_is_deterministic():
    text = "Totally unrelated message."
    assert format_ticket_json(text) == format_ticket_json(text)