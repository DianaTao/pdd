"""
Deterministic CI gate for prompt contracts.

Orchestrates the full deterministic pipeline in a single call:
  Stage 1: prompt lint (no LLM)
  Stage 2: contracts check (no LLM)
  Stage 3: contracts compile
  Stage 4: coverage --contracts

100% deterministic — zero LLM calls.  This is the key invariant.
Tests and service consumers may call run_gate() directly without Click.

Public API
----------
run_gate(target, stories_dir, tests_dir, strict, skip_stories_lint) -> GateRun
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .contract_check import check_directory, check_prompt
from .contract_compile import compile_directory, compile_prompt
from .coverage_contracts import CoverageResult, build_coverage, build_coverage_directory
from .prompt_lint import scan_prompt, scan_stories

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    """Result of one gate stage."""

    name: str
    exit_code: int  # 0=pass, 1=warn, 2=fail
    error_count: int
    warn_count: int
    detail: str  # short human summary
    skipped: bool = False

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "exit_code": self.exit_code,
            "error_count": self.error_count,
            "warn_count": self.warn_count,
            "detail": self.detail,
            "skipped": self.skipped,
        }


@dataclass
class GateRun:
    """Aggregated result of a full contracts gate run."""

    target: Path
    stages: list[StageResult] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """Worst exit_code across all non-skipped stages."""
        return max((s.exit_code for s in self.stages if not s.skipped), default=0)

    def as_dict(self) -> dict:
        return {
            "target": str(self.target),
            "exit_code": self.exit_code,
            "stages": [s.as_dict() for s in self.stages],
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _stage_prompt_lint(
    path: Path,
    stories_dir: Optional[Path],
    *,
    strict: bool,
    skip_stories_lint: bool,
) -> StageResult:
    """Stage 1: deterministic prompt lint (no LLM)."""
    paths = [path] if path.is_file() else sorted(path.rglob("*.prompt"))
    all_issues = []
    for p in paths:
        if p.name.lower().endswith("_llm.prompt"):
            continue
        result = scan_prompt(p, strict=strict)
        all_issues.extend(result.issues)

    if not skip_stories_lint and stories_dir and stories_dir.is_dir():
        story_results = scan_stories(stories_dir, strict=strict)
        for r in story_results:
            all_issues.extend(r.issues)

    errors = sum(1 for i in all_issues if i.level == "error")
    warns = sum(1 for i in all_issues if i.level == "warning")
    code = 2 if errors > 0 else (1 if warns > 0 else 0)
    return StageResult(
        name="prompt-lint",
        exit_code=code,
        error_count=errors,
        warn_count=warns,
        detail=f"errors={errors} warns={warns}",
    )


def _stage_contracts_check(
    path: Path,
    stories_dir: Optional[Path],
    *,
    strict: bool,
) -> StageResult:
    """Stage 2: contracts check (structural authoring)."""
    if path.is_file():
        results = [check_prompt(path, strict=strict)]
    else:
        results = check_directory(path, strict=strict)

    errors = sum(r.error_count for r in results)
    warns = sum(r.warn_count for r in results)
    code = 2 if errors > 0 else (1 if warns > 0 else 0)
    return StageResult(
        name="contracts-check",
        exit_code=code,
        error_count=errors,
        warn_count=warns,
        detail=f"errors={errors} warns={warns}",
    )


def _stage_contracts_compile(path: Path) -> StageResult:
    """Stage 3: compile contract rules into deterministic IR."""
    if path.is_file():
        results = [compile_prompt(path)]
    else:
        results = compile_directory(path)

    errors = sum(r.error_count for r in results)
    rules = sum(r.rule_count for r in results)
    code = 2 if errors > 0 else 0
    return StageResult(
        name="contracts-compile",
        exit_code=code,
        error_count=errors,
        warn_count=0,
        detail=f"rules={rules} errors={errors}",
    )


def _stage_coverage(
    path: Path,
    stories_dir: Optional[Path],
    tests_dir: Optional[Path],
    *,
    strict: bool,
) -> StageResult:
    """Stage 4: coverage -- contracts."""
    if path.is_file():
        results: list[CoverageResult] = [build_coverage(path, stories_dir, tests_dir)]
    else:
        results = build_coverage_directory(path, stories_dir, tests_dir)

    total_unchecked = sum(
        r.summary.get("unchecked", 0) for r in results if r.summary
    )
    total_checked = sum(
        r.summary.get("checked", 0) for r in results if r.summary
    )
    total_rules = sum(
        r.summary.get("total", 0) for r in results if r.summary
    )

    if strict and total_unchecked > 0:
        code = 2
    elif total_unchecked > 0:
        code = 1
    else:
        code = 0

    return StageResult(
        name="coverage",
        exit_code=code,
        error_count=total_unchecked if strict else 0,
        warn_count=total_unchecked if not strict else 0,
        detail=f"total={total_rules} checked={total_checked} unchecked={total_unchecked}",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_gate(
    target: Path,
    *,
    stories_dir: Optional[Path] = None,
    tests_dir: Optional[Path] = None,
    strict: bool = False,
    skip_stories_lint: bool = False,
) -> GateRun:
    """
    Run all deterministic gate stages and return a GateRun.

    No LLM calls are made.  Any stage that exits >= 2 causes subsequent
    stages to be marked skipped (fail-fast).

    Args:
        target: prompt file or directory of .prompt files.
        stories_dir: optional user-stories directory.
        tests_dir: optional tests directory for coverage.
        strict: treat warnings as errors in coverage stage.
        skip_stories_lint: skip story scanning in stage 1.

    Returns:
        GateRun with all stage results and overall exit_code.
    """
    run = GateRun(target=target)

    stage1 = _stage_prompt_lint(
        target,
        stories_dir,
        strict=strict,
        skip_stories_lint=skip_stories_lint,
    )
    run.stages.append(stage1)
    if stage1.exit_code >= 2:
        for name in ("contracts-check", "contracts-compile", "coverage"):
            run.stages.append(
                StageResult(name=name, exit_code=0, error_count=0, warn_count=0, detail="skipped", skipped=True)
            )
        return run

    stage2 = _stage_contracts_check(target, stories_dir, strict=strict)
    run.stages.append(stage2)
    if stage2.exit_code >= 2:
        for name in ("contracts-compile", "coverage"):
            run.stages.append(
                StageResult(name=name, exit_code=0, error_count=0, warn_count=0, detail="skipped", skipped=True)
            )
        return run

    stage3 = _stage_contracts_compile(target)
    run.stages.append(stage3)
    if stage3.exit_code >= 2:
        run.stages.append(
            StageResult(name="coverage", exit_code=0, error_count=0, warn_count=0, detail="skipped", skipped=True)
        )
        return run

    stage4 = _stage_coverage(target, stories_dir, tests_dir, strict=strict)
    run.stages.append(stage4)

    return run
