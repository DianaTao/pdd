"""
LLM-assisted contract authoring for prompts that lack <contract_rules>.

Two modes:
  greenfield  -- prompt exists, no code; LLM designs rules from requirements.
  retrofit    -- prompt + code exist; LLM infers rules from existing behaviour.

The module asks the LLM to produce <contract_rules>, <vocabulary>, and
<acceptance_tests> blocks, then optionally writes them back into the prompt
via prompt_block_writeback helpers.

Public API
----------
author_contracts(prompt_path, code_path, mode, strength, temperature, verbose,
                 dry_run) -> AuthorResult
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .contract_ir import extract_sections
from .prompt_block_writeback import (
    append_acceptance_tests,
    append_contract_rules,
    append_formalization,
)
from .prompt_lint import append_vocabulary_definitions
from .prompt_lint_schemas import FormalizationCandidate

logger = logging.getLogger(__name__)

MODE_GREENFIELD = "greenfield"
MODE_RETROFIT = "retrofit"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AuthorResult:
    """Result of one contracts author run."""

    prompt_path: str
    mode: str
    suggested_rules: list[str] = field(default_factory=list)
    suggested_vocabulary: list[str] = field(default_factory=list)
    suggested_acceptance_tests: list[str] = field(default_factory=list)
    rules_written: int = 0
    acceptance_tests_written: int = 0
    skipped: bool = False          # True if <contract_rules> already present without --force
    dry_run: bool = False
    error: Optional[str] = None
    # Post-write quality metrics (populated after writeback; 0/-1 when not applicable)
    compile_errors: int = 0
    new_lint_warnings: int = 0
    quality_ok: bool = True
    # Formalization block (populated only when --formalize is used)
    formalization_written: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_path": self.prompt_path,
            "mode": self.mode,
            "suggested_rules": self.suggested_rules,
            "suggested_vocabulary": self.suggested_vocabulary,
            "suggested_acceptance_tests": self.suggested_acceptance_tests,
            "rules_written": self.rules_written,
            "acceptance_tests_written": self.acceptance_tests_written,
            "skipped": self.skipped,
            "dry_run": self.dry_run,
            "error": self.error,
            "compile_errors": self.compile_errors,
            "new_lint_warnings": self.new_lint_warnings,
            "quality_ok": self.quality_ok,
            "formalization_written": self.formalization_written,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_mode(prompt_path: Path, code_path: Optional[Path]) -> str:
    """Auto-detect mode: retrofit if code file exists, else greenfield."""
    if code_path and code_path.is_file():
        return MODE_RETROFIT
    return MODE_GREENFIELD


def _build_author_context(
    prompt_path: Path,
    code_path: Optional[Path],
    mode: str,
) -> dict[str, Any]:
    """Build the JSON context passed to the LLM template."""
    prompt_text = prompt_path.read_text(encoding="utf-8")
    sections = extract_sections(prompt_text)
    # Remove heavy generated content from context
    requirements = (
        sections.get("requirements", "")
        or sections.get("prompt", prompt_text[:4000])
    )
    ctx: dict[str, Any] = {
        "mode": mode,
        "prompt_path": str(prompt_path),
        "requirements": requirements[:4000],
        "existing_contract_rules": sections.get("contract_rules", ""),
        "existing_vocabulary": sections.get("vocabulary", ""),
    }
    if code_path and code_path.is_file():
        code_text = code_path.read_text(encoding="utf-8")
        ctx["code_snippet"] = code_text[:6000]
    return ctx


def _parse_author_response(raw: str) -> dict[str, Any]:
    """Extract the JSON payload from LLM response."""
    for i, ch in enumerate(raw):
        if ch in "{[":
            try:
                payload = json.loads(raw[i:])
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass
    return {}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def author_contracts(
    prompt_path: Path,
    code_path: Optional[Path] = None,
    *,
    mode: Optional[str] = None,
    strength: float = 0.5,
    temperature: float = 0.1,
    time: Optional[float] = None,
    verbose: bool = False,
    dry_run: bool = False,
    force: bool = False,
    formalize: bool = False,
) -> AuthorResult:
    """
    Run LLM-assisted contract authoring.

    Args:
        prompt_path: target .prompt file.
        code_path: paired code file (for retrofit mode).  Auto-detected if None.
        mode: "greenfield" | "retrofit" | None (auto-detect).
        dry_run: return suggestions without writing to the prompt file.
        force: overwrite existing <contract_rules> if present.
        formalize: after writing rules, also invoke the formalize LLM to append
                   a <formalization> block with Z3/SMT targets.

    Returns:
        AuthorResult with suggestions and write counts.
    """
    result = AuthorResult(prompt_path=str(prompt_path), mode=mode or "auto", dry_run=dry_run)

    # Guard: existing rules
    text = prompt_path.read_text(encoding="utf-8")
    sections = extract_sections(text)
    if sections.get("contract_rules") and not force:
        result.skipped = True
        return result

    # Resolve mode
    resolved_mode = mode or _detect_mode(prompt_path, code_path)
    result.mode = resolved_mode

    try:
        from .llm_invoke import llm_invoke  # pylint: disable=import-outside-toplevel
        from .preprocess import preprocess  # pylint: disable=import-outside-toplevel
    except ImportError:
        result.error = "LLM dependencies not available."
        return result

    try:
        template_path = Path(__file__).parent / "prompts" / "contract_author_LLM.prompt"
        template = template_path.read_text(encoding="utf-8")

        context = _build_author_context(prompt_path, code_path, resolved_mode)
        # Replace both placeholders before calling preprocess
        filled = (
            template
            .replace("{mode}", resolved_mode)
            .replace("{author_context_json}", json.dumps(context, indent=2))
        )
        filled = preprocess(filled, recursive=False, double_curly_brackets=False)

        llm_result = llm_invoke(
            messages=[{"role": "user", "content": filled}],
            strength=strength,
            temperature=temperature,
            time=time,
            verbose=verbose,
            use_cloud=True,
        )

        # llm_invoke returns {"result": "...", ...} — "result" is the canonical key
        raw = llm_result["result"] if isinstance(llm_result, dict) else str(llm_result)
        payload = _parse_author_response(raw)

        result.suggested_rules = payload.get("contract_rules", [])
        result.suggested_vocabulary = payload.get("vocabulary", [])
        result.suggested_acceptance_tests = payload.get("acceptance_tests", [])

    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Contract author LLM pass failed: %s", exc)
        result.error = str(exc)
        return result

    if dry_run or result.error:
        return result

    # Write back all three sections
    if result.suggested_rules:
        result.rules_written = append_contract_rules(prompt_path, result.suggested_rules)
    if result.suggested_acceptance_tests:
        result.acceptance_tests_written = append_acceptance_tests(
            prompt_path, result.suggested_acceptance_tests
        )
    if result.suggested_vocabulary:
        append_vocabulary_definitions(prompt_path, result.suggested_vocabulary)

    # Optional: invoke formalize LLM to append <formalization> block
    if formalize:
        try:
            from .contract_compile import compile_prompt  # pylint: disable=import-outside-toplevel

            formalize_template_path = (
                Path(__file__).parent / "prompts" / "prompt_formalize_LLM.prompt"
            )
            formalize_template = formalize_template_path.read_text(encoding="utf-8")
            enriched_prompt = prompt_path.read_text(encoding="utf-8")
            ir = compile_prompt(prompt_path)
            guidance_json = json.dumps(ir.as_dict(), indent=2)

            filled_formalize = (
                formalize_template
                .replace("{prompt_content}", enriched_prompt)
                .replace("{guidance_json}", guidance_json)
            )

            llm_formal = llm_invoke(
                messages=[{"role": "user", "content": filled_formalize}],
                strength=strength,
                temperature=temperature,
                time=time,
                verbose=verbose,
                use_cloud=True,
            )
            raw_formal = (
                llm_formal["result"]
                if isinstance(llm_formal, dict)
                else str(llm_formal)
            )
            formal_payload = _parse_author_response(raw_formal)
            candidates_raw = formal_payload.get("formalization", [])
            candidates = []
            for item in candidates_raw:
                if isinstance(item, dict):
                    try:
                        candidates.append(FormalizationCandidate(**{
                            k: v for k, v in item.items()
                            if k in FormalizationCandidate.model_fields
                        }))
                    except Exception:  # pylint: disable=broad-except
                        pass
            if candidates:
                result.formalization_written = append_formalization(prompt_path, candidates)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Formalize LLM pass failed: %s", exc)

    # Post-write validation: deterministic compile + lint, no LLM required
    try:
        from .contract_compile import compile_prompt  # pylint: disable=import-outside-toplevel
        from .contract_check import check_prompt  # pylint: disable=import-outside-toplevel

        ir = compile_prompt(prompt_path)
        result.compile_errors = ir.error_count

        lint = check_prompt(prompt_path)
        result.new_lint_warnings = lint.warn_count
        result.quality_ok = (ir.error_count == 0 and lint.error_count == 0)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Post-write validation failed: %s", exc)

    return result
