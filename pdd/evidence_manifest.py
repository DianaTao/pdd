"""
Evidence manifest service.

Produces a detailed, per-rule evidence report for a prompt — richer than
``pdd coverage --contracts``, which only shows status counts.  For each rule
this collects the *content* of the evidence: story acceptance-criteria snippets,
test function names, and formalization predicate text.

100% deterministic.  No LLM calls.

Public API
----------
build_manifest(path, stories_dir, tests_dir) -> EvidenceManifest
emit_manifest(path, stories_dir, tests_dir, *, output_path) -> EvidenceManifest
validate_manifest(path) -> ManifestValidation
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .coverage_contracts import (
    CoverageResult,
    RuleCoverage,
    STATUS_UNCHECKED,
    build_coverage,
)
from .contract_compile import compile_prompt
from .contract_ir import extract_sections

SCHEMA = "pdd.evidence.manifest.v1"

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RuleEvidence:
    """Full evidence payload for one contract rule."""

    rule_id: str
    status: str
    stories: list[str]
    story_snippets: list[str]   # AC text excerpts, one per linked story
    tests: list[str]            # test function names
    formal: list[str]           # formalization predicate blocks
    waiver: Optional[str]
    gap: bool                   # True when status is unchecked or story-only with no test

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "status": self.status,
            "stories": self.stories,
            "story_snippets": self.story_snippets,
            "tests": self.tests,
            "formal": self.formal,
            "waiver": self.waiver,
            "gap": self.gap,
        }


@dataclass
class EvidenceManifest:
    """Evidence manifest for one prompt file."""

    schema: str
    generated_at: str
    prompt_path: str
    prompt_sha256: str
    rule_count: int
    rules: list[RuleEvidence] = field(default_factory=list)
    gap_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "prompt_path": self.prompt_path,
            "prompt_sha256": self.prompt_sha256,
            "rule_count": self.rule_count,
            "gap_count": self.gap_count,
            "rules": [r.as_dict() for r in self.rules],
        }


@dataclass
class ManifestValidation:
    """Result of validating a stored manifest file."""

    path: str
    valid: bool
    schema: str
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "valid": self.valid,
            "schema": self.schema,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_AC_HEADING_RE = re.compile(
    r"##\s+acceptance\s+criteria\b",
    re.IGNORECASE,
)
_NEXT_HEADING_RE = re.compile(r"^##", re.MULTILINE)
_COVERS_RE = re.compile(
    r"##\s+covers\b.*?(?=^##|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _story_ac_snippet(story_path: Path, max_chars: int = 400) -> str:
    """Return the text under the Acceptance Criteria heading of a story file."""
    try:
        text = story_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = _AC_HEADING_RE.search(text)
    if not m:
        return ""
    start = m.end()
    # next heading or EOF
    nxt = _NEXT_HEADING_RE.search(text, start)
    snippet = text[start: nxt.start() if nxt else len(text)].strip()
    return snippet[:max_chars] + ("…" if len(snippet) > max_chars else "")


def _formal_blocks(prompt_path: Path, rule_id: str) -> list[str]:
    """Extract formalization predicate blocks for rule_id."""
    try:
        text = prompt_path.read_text(encoding="utf-8")
    except OSError:
        return []
    sections = extract_sections(text)
    formal_text = sections.get("formalization", "")
    if not formal_text:
        return []
    # Split on rule ID headings: R1:  R2:  etc.
    id_pat = re.compile(r"^" + re.escape(rule_id) + r"\s*:", re.MULTILINE | re.IGNORECASE)
    m = id_pat.search(formal_text)
    if not m:
        return []
    start = m.start()
    # find next rule heading or EOF
    next_rule = re.compile(r"^(R-?\d+|RULE-?\d+)\s*:", re.MULTILINE | re.IGNORECASE)
    following = next_rule.search(formal_text, m.end())
    block = formal_text[start: following.start() if following else len(formal_text)].strip()
    return [block] if block else []


def _enrich_rule(
    rule: RuleCoverage,
    stories_dir: Optional[Path],
    prompt_path: Path,
) -> RuleEvidence:
    """Turn a RuleCoverage into a RuleEvidence with content snippets."""
    snippets: list[str] = []
    if stories_dir and stories_dir.is_dir():
        for story_name in rule.stories:
            # story_name may be just a filename or a relative path
            candidate = stories_dir / story_name
            if not candidate.is_file():
                # try glob
                hits = list(stories_dir.rglob(story_name))
                candidate = hits[0] if hits else candidate
            if candidate.is_file():
                snippet = _story_ac_snippet(candidate)
                if snippet:
                    snippets.append(snippet)

    formal = _formal_blocks(prompt_path, rule.rule_id)
    gap = rule.status in (STATUS_UNCHECKED,) or (
        rule.status == "story-only" and not rule.tests
    )
    return RuleEvidence(
        rule_id=rule.rule_id,
        status=rule.status,
        stories=list(rule.stories),
        story_snippets=snippets,
        tests=list(rule.tests),
        formal=formal,
        waiver=rule.waiver,
        gap=gap,
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def build_manifest(
    prompt_path: Path,
    stories_dir: Optional[Path] = None,
    tests_dir: Optional[Path] = None,
) -> EvidenceManifest:
    """Build an EvidenceManifest for *prompt_path* without writing it to disk."""
    coverage: CoverageResult = build_coverage(prompt_path, stories_dir, tests_dir)
    rules_evidence = [
        _enrich_rule(rule, stories_dir, prompt_path)
        for rule in coverage.rules
    ]
    gap_count = sum(1 for r in rules_evidence if r.gap)
    return EvidenceManifest(
        schema=SCHEMA,
        generated_at=datetime.now(timezone.utc).isoformat(),
        prompt_path=str(prompt_path),
        prompt_sha256=_sha256(prompt_path),
        rule_count=len(rules_evidence),
        rules=rules_evidence,
        gap_count=gap_count,
    )


def emit_manifest(
    prompt_path: Path,
    stories_dir: Optional[Path] = None,
    tests_dir: Optional[Path] = None,
    *,
    output_path: Optional[Path] = None,
) -> EvidenceManifest:
    """
    Build and write an EvidenceManifest.

    If *output_path* is None the manifest is returned but not written.
    Returns the EvidenceManifest.
    """
    manifest = build_manifest(prompt_path, stories_dir, tests_dir)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(manifest.as_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
    return manifest


def validate_manifest(manifest_path: Path) -> ManifestValidation:
    """
    Validate a stored manifest JSON file.

    Checks: schema field present, required top-level keys, non-empty rules list.
    """
    errors: list[str] = []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ManifestValidation(
            path=str(manifest_path),
            valid=False,
            schema="",
            errors=[str(exc)],
        )

    schema = data.get("schema", "")
    if schema != SCHEMA:
        errors.append(f"schema mismatch: expected {SCHEMA!r}, got {schema!r}")

    for key in ("generated_at", "prompt_path", "prompt_sha256", "rule_count", "rules"):
        if key not in data:
            errors.append(f"missing required key: {key!r}")

    return ManifestValidation(
        path=str(manifest_path),
        valid=len(errors) == 0,
        schema=schema,
        errors=errors,
    )
