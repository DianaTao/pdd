"""Few-shot mold for GitHub issue classification (safe to compress)."""

# Long redundant module notes that compression should strip.
# These comments describe historical context but do not change behavior.
# They exist only to inflate token count for the demo.


def classify_issue(title: str, body: str) -> dict[str, str]:
    """Return category and severity for a GitHub issue title/body pair."""
    text = f"{title}\n{body}".lower()
    if "crash" in text or "error" in text:
        return {"category": "bug", "severity": "high"}
    if "dark mode" in text or "feature" in text:
        return {"category": "feature_request", "severity": "medium"}
    if "docs" in text or "documentation" in text:
        return {"category": "documentation", "severity": "low"}
    return {"category": "other", "severity": "low"}


def format_issue_json(title: str, body: str) -> str:
    """Serialize classification as JSON for prompt few-shot outputs."""
    import json

    return json.dumps(classify_issue(title, body), sort_keys=True)
