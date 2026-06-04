"""Marketplace few-shot code: bug severity pattern."""

import json


def classify_ticket(text: str) -> dict[str, str]:
    """Classify support text; crashes and errors are high-severity bugs."""
    lowered = text.lower()
    if "crash" in lowered or "error" in lowered or "500" in lowered:
        return {"category": "bug", "severity": "high"}
    return {"category": "other", "severity": "low"}


def format_ticket_json(text: str) -> str:
    """Serialize classifier output as compact JSON."""
    return json.dumps(classify_ticket(text), sort_keys=True)
