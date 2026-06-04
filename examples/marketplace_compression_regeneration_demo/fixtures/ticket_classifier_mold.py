"""Representative local mold paired with marketplace few-shot examples."""

import json


def classify_ticket(text: str) -> dict[str, str]:
    """Classify a user ticket into category and severity labels."""
    lowered = text.lower()
    if "crash" in lowered or "error" in lowered:
        return {"category": "bug", "severity": "high"}
    if "add" in lowered or "please" in lowered:
        return {"category": "feature_request", "severity": "medium"}
    if "readme" in lowered or "docs" in lowered:
        return {"category": "documentation", "severity": "low"}
    if "slow" in lowered or "mobile" in lowered:
        return {"category": "usability", "severity": "medium"}
    return {"category": "other", "severity": "low"}


def format_ticket_json(text: str) -> str:
    """Return deterministic compact JSON for the classifier result."""
    return json.dumps(classify_ticket(text), sort_keys=True)
