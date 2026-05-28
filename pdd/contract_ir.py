from __future__ import annotations

import re
from pathlib import Path

# Regex to find <contract_rules>...</contract_rules> blocks
CONTRACT_RULES_RE = re.compile(
    r"<contract_rules>(?P<content>[\s\S]*?)</contract_rules>",
    re.IGNORECASE
)

# Regex to find rule ID at the start of a line (e.g. R1)
RULE_ID_SPLIT_RE = re.compile(
    r"^\s*(R\d+)\b",
    re.MULTILINE
)


def parse_prompt_contracts(prompt_content: str) -> list[dict[str, str]]:
    """
    Parses <contract_rules> from prompt content and extracts rule IDs and summaries.
    Returns a list of dictionaries with keys: 'id', 'summary', 'text'.
    """
    matches = CONTRACT_RULES_RE.findall(prompt_content)
    if not matches:
        return []

    rules = []
    for block in matches:
        parts = RULE_ID_SPLIT_RE.split(block)
        # parts[0] is everything before the first rule ID
        # subsequent parts are alternating rule_id and rule_body
        for i in range(1, len(parts), 2):
            rule_id = parts[i].strip()
            body = parts[i+1] if i+1 < len(parts) else ""
            
            # Clean up the body
            body_lines = [line.strip() for line in body.splitlines() if line.strip()]
            if not body_lines:
                continue
                
            # First line might contain a name/title (e.g., "- Positive amount")
            first_line = body_lines[0]
            # Strip leading non-alphanumeric chars (like "-", ":", spaces) from first line
            first_line_cleaned = re.sub(r"^[^a-zA-Z0-9]+", "", first_line).strip()
            
            # Determine summary
            if len(body_lines) > 1 and len(first_line_cleaned) < 80:
                summary = first_line_cleaned
                full_text = "\n".join(body_lines[1:])
            else:
                summary = first_line_cleaned
                full_text = "\n".join(body_lines)
                
            # If summary is too long, truncate it
            if len(summary) > 120:
                summary = summary[:117] + "..."
                
            rules.append({
                "id": rule_id,
                "summary": summary,
                "text": "\n".join(body_lines),
            })
            
    return rules
