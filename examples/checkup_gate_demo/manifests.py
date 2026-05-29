"""Helpers to build evidence manifests for ``pdd checkup gate`` demos."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_demo_manifest(
    path: Path,
    *,
    basename: str,
    output_rel: str,
    output_hash: str,
    validation: dict[str, str],
    prompt_rel: str | None = None,
    cost_usd: float = 1.0,
) -> Path:
    """Write a minimal schema-v1 dev-unit manifest for gate demonstrations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_rel or f"prompts/{basename}_demo_python.prompt"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "run": {
            "id": f"demo-{basename}",
            "command": "pdd sync",
            "pdd_version": "demo",
            "timestamp": "2026-01-01T00:00:00Z",
        },
        "prompt": {
            "path": prompt_path,
            "sha256": "a" * 64,
            "expanded_sha256": None,
            "uses_nondeterministic_tags": False,
        },
        "context": {"includes": [], "web_snapshots": [], "shell_snapshots": []},
        "generation": {
            "model": "demo",
            "temperature": 0.0,
            "cost_usd": cost_usd,
            "grounding_examples": [],
        },
        "outputs": [{"path": output_rel, "sha256": output_hash}],
        "contracts": {"status": "not_applicable", "rules": {}},
        "validation": validation,
        "logs": {"core_dump": None, "verify_results": None, "cost_csv": None},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
