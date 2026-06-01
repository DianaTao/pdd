#!/usr/bin/env python3
"""Offline demonstration of grounding evidence mapping and policy checks (#827)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pdd.grounding_policy import check, load_policy
from pdd.grounding_provenance import (
    build_grounding_metadata,
    reviewed_from_decisions,
    selected_examples_from_cloud,
)

CLOUD_EXAMPLES_USED = [{"id": "payments", "title": "Payments example"}]


def main() -> None:
    selected = selected_examples_from_cloud(CLOUD_EXAMPLES_USED)
    print("=== examplesUsed → selected_examples (id/title regression) ===")
    print(json.dumps(selected, indent=2))
    assert selected, "id/title cloud records must not map to an empty list"

    pre_decisions = [{"module": "payments", "decision": "accept", "phase": "pre"}]
    reviewed = reviewed_from_decisions(pre_decisions, examples_used=CLOUD_EXAMPLES_USED)
    grounding = build_grounding_metadata(
        mode="cloud",
        examples_used=CLOUD_EXAMPLES_USED,
        grounding_overrides={"pinned": ["payments"], "excluded": []},
        reviewed=reviewed,
    )
    print("\n=== generation.grounding (pre-approved cloud example) ===")
    print(json.dumps(grounding, indent=2))
    assert grounding["reviewed"] is True

    policy_path = Path(__file__).parent / ".pdd" / "grounding_policy.yaml"
    policy = load_policy(str(policy_path))
    violations = check(policy, "payments", grounding)
    print("\n=== policy check (payments, satisfied) ===")
    print(json.dumps([v.model_dump() for v in violations], indent=2))

    not_reviewed = dict(grounding)
    not_reviewed["reviewed"] = False
    violations_missing = check(policy, "payments", not_reviewed)
    print("\n=== policy check (payments, reviewed=false → expect review_required) ===")
    print(json.dumps([v.model_dump() for v in violations_missing], indent=2))
    assert any(v.code == "grounding.review_required" for v in violations_missing)

    print("\nDemo OK.")


if __name__ == "__main__":
    main()
