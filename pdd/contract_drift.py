"""
Contract drift detection.

Two orthogonal checks in one module:

1. Structural drift (deterministic)
   Scans code for terms referenced by MUST NOT rules and flags matches.
   E.g. "MUST NOT call cache_client" → grep for `cache_client` in code.
   Safe to run in CI (no LLM).

2. Semantic drift (LLM, advisory)
   Asks an LLM whether each MUST obligation appears to be implemented
   in the paired code file.  Never a hard gate; always exits 0 unless
   --strict is passed explicitly.

Public API
----------
structural_drift(prompt_path, code_path) -> list[DriftFinding]
semantic_drift(prompt_path, code_path, strength, temperature, verbose) -> DriftResult
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .contract_compile import compile_prompt
from .contract_ir import parse_prompt_contracts

logger = logging.getLogger(__name__)

FINDING_KIND_STRUCTURAL = "structural"
FINDING_KIND_SEMANTIC = "semantic"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DriftFinding:
    """One drift finding."""

    kind: str            # "structural" | "semantic"
    rule_id: str
    message: str
    term: str = ""       # the specific term / obligation that drifted
    line: str = ""       # code line that triggered a structural find
    line_number: int = 0
    confidence: str = "medium"  # for semantic findings

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "rule_id": self.rule_id,
            "message": self.message,
            "term": self.term,
            "line": self.line,
            "line_number": self.line_number,
            "confidence": self.confidence,
        }


@dataclass
class DriftResult:
    """Aggregated drift report for (prompt, code)."""

    prompt_path: str
    code_path: str
    structural_findings: list[DriftFinding] = field(default_factory=list)
    semantic_findings: list[DriftFinding] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def has_drift(self) -> bool:
        return bool(self.structural_findings or self.semantic_findings)

    @property
    def finding_count(self) -> int:
        return len(self.structural_findings) + len(self.semantic_findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_path": self.prompt_path,
            "code_path": self.code_path,
            "has_drift": self.has_drift,
            "finding_count": self.finding_count,
            "structural_findings": [f.as_dict() for f in self.structural_findings],
            "semantic_findings": [f.as_dict() for f in self.semantic_findings],
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Structural drift (deterministic)
# ---------------------------------------------------------------------------

_MUST_NOT_CALL_RE = re.compile(
    r"MUST\s+NOT\s+(?:call|invoke|use)\s+(\w[\w.]+)",
    re.IGNORECASE,
)
_MUST_NOT_WRITE_RE = re.compile(
    r"MUST\s+NOT\s+(?:write|store|mutate|modify)\s+([\w.]+)",
    re.IGNORECASE,
)
_MUST_NOT_READ_RE = re.compile(
    r"MUST\s+NOT\s+(?:read|access)\s+([\w.]+)",
    re.IGNORECASE,
)


def _extract_must_not_terms(rule_text: str) -> list[str]:
    """Extract identifiers from MUST NOT clauses that can be searched in code."""
    terms: list[str] = []
    for pattern in (_MUST_NOT_CALL_RE, _MUST_NOT_WRITE_RE, _MUST_NOT_READ_RE):
        terms.extend(m.group(1) for m in pattern.finditer(rule_text))
    return terms


def structural_drift(
    prompt_path: Path,
    code_path: Path,
) -> list[DriftFinding]:
    """
    Deterministic structural drift check.

    Finds cases where a MUST NOT clause references a term (function, variable,
    module) and that term appears in the code file.

    Returns a list of DriftFinding with kind="structural".
    Safe to use in CI — no LLM.
    """
    findings: list[DriftFinding] = []

    ir = compile_prompt(prompt_path)
    if not ir.has_contract_rules:
        return findings

    try:
        code_lines = code_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Cannot read code file %s: %s", code_path, exc)
        return findings

    for rule in ir.rules:
        rule_text = rule.raw or ""
        must_not_terms = _extract_must_not_terms(rule_text)
        for term in must_not_terms:
            # Simple token search (word boundary)
            term_re = re.compile(r"\b" + re.escape(term) + r"\b")
            for lineno, line in enumerate(code_lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue  # skip comments
                if term_re.search(line):
                    findings.append(DriftFinding(
                        kind=FINDING_KIND_STRUCTURAL,
                        rule_id=rule.id,
                        message=(
                            f"Rule {rule.id} says MUST NOT use '{term}' "
                            f"but it appears in code at line {lineno}."
                        ),
                        term=term,
                        line=line.rstrip(),
                        line_number=lineno,
                    ))
                    break  # one finding per term per rule is enough

    return findings


# ---------------------------------------------------------------------------
# Semantic drift (LLM, advisory)
# ---------------------------------------------------------------------------


def semantic_drift(
    prompt_path: Path,
    code_path: Path,
    *,
    strength: float = 0.5,
    temperature: float = 0.0,
    time: Optional[float] = None,
    verbose: bool = False,
) -> DriftResult:
    """
    LLM-based semantic drift check (advisory only).

    Asks whether each MUST obligation in the prompt is implemented in the
    paired code file.  Returns a DriftResult; always exits 0 unless the
    caller explicitly checks findings and enforces --strict.
    """
    result = DriftResult(
        prompt_path=str(prompt_path),
        code_path=str(code_path),
    )

    # Run structural check first
    result.structural_findings = structural_drift(prompt_path, code_path)

    ir = compile_prompt(prompt_path)
    if not ir.has_contract_rules:
        return result

    try:
        code_text = code_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.error = f"Cannot read code file: {exc}"
        return result

    try:
        from .llm_invoke import llm_invoke  # pylint: disable=import-outside-toplevel
        from .preprocess import preprocess  # pylint: disable=import-outside-toplevel
    except ImportError:
        logger.warning("LLM dependencies not available; skipping semantic drift.")
        return result

    try:
        template_path = Path(__file__).parent / "prompts" / "contract_drift_LLM.prompt"
        template = template_path.read_text(encoding="utf-8")

        context = {
            "prompt_path": str(prompt_path),
            "code_path": str(code_path),
            "rules": [r.as_dict() for r in ir.rules],
            "code_snippet": code_text[:8000],  # limit context size
        }
        filled = template.replace("{drift_context_json}", json.dumps(context, indent=2))
        filled = preprocess(filled, recursive=False, double_curly_brackets=False)

        llm_result = llm_invoke(
            messages=[{"role": "user", "content": filled}],
            strength=strength,
            temperature=temperature,
            time=time,
            verbose=verbose,
            use_cloud=True,
        )

        raw = llm_result["result"] if isinstance(llm_result, dict) else str(llm_result)
        # Extract JSON from the response
        for i, ch in enumerate(raw):
            if ch in "{[":
                try:
                    payload = json.loads(raw[i:])
                    break
                except json.JSONDecodeError:
                    pass
        else:
            payload = {}

        findings_raw = payload if isinstance(payload, list) else payload.get("findings", [])
        for item in findings_raw:
            result.semantic_findings.append(DriftFinding(
                kind=FINDING_KIND_SEMANTIC,
                rule_id=item.get("rule_id", ""),
                message=item.get("message", ""),
                term=item.get("term", ""),
                confidence=item.get("confidence", "medium"),
            ))

    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Semantic drift LLM pass failed: %s", exc)
        result.error = str(exc)

    return result
