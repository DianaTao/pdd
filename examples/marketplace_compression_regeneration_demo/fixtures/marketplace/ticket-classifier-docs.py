"""Marketplace few-shot code: documentation severity pattern."""

import json


def classify_ticket(text: str) -> dict[str, str]:
    """Classify support text; documentation gaps are low severity."""
    lowered = text.lower()
    if "readme" in lowered or "docs" in lowered or "documentation" in lowered:
        return {"category": "documentation", "severity": "low"}
    return {"category": "other", "severity": "low"}


def format_ticket_json(text: str) -> str:
    """Serialize classifier output as compact JSON."""
    return json.dumps(classify_ticket(text), sort_keys=True)
