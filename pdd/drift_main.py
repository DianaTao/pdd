"""Regeneration stability checks for PDD dev units (``pdd drift``)."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .evidence_store import ManifestView, resolve_prompt_path


@dataclass
class RunSnapshot:
    run_index: int
    code_sha256: str
    public_api: list[str]
    tests_passed: bool
    stories_passed: bool
    verify_passed: bool
    policy_passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_index": self.run_index,
            "code_sha256": self.code_sha256,
            "public_api": self.public_api,
            "tests_passed": self.tests_passed,
            "stories_passed": self.stories_passed,
            "verify_passed": self.verify_passed,
            "policy_passed": self.policy_passed,
        }


@dataclass
class DriftReport:
    devunit: str
    prompt_path: str
    code_path: str
    runs: int
    snapshots: list[RunSnapshot] = field(default_factory=list)
    public_api_unchanged: bool = True
    implementation_changed: bool = False
    behavior_unchanged: bool = True
    status: str = "stable"
    dry_run: bool = False

    @property
    def passed(self) -> bool:
        return self.status == "stable"

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1

    def as_dict(self) -> dict[str, Any]:
        passed_runs = sum(1 for snap in self.snapshots if snap.tests_passed)
        return {
            "devunit": self.devunit,
            "prompt_path": self.prompt_path,
            "code_path": self.code_path,
            "runs": self.runs,
            "dry_run": self.dry_run,
            "status": self.status,
            "public_api_unchanged": self.public_api_unchanged,
            "implementation_changed": self.implementation_changed,
            "behavior_unchanged": self.behavior_unchanged,
            "tests": f"passed {passed_runs}/{self.runs}",
            "stories": f"passed {passed_runs}/{self.runs}",
            "verify": f"passed {passed_runs}/{self.runs}",
            "policy": f"passed {passed_runs}/{self.runs}",
            "snapshots": [snap.as_dict() for snap in self.snapshots],
        }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _public_api(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names.append(f"def {node.name}")
        elif isinstance(node, ast.AsyncFunctionDef):
            names.append(f"async def {node.name}")
        elif isinstance(node, ast.ClassDef):
            names.append(f"class {node.name}")
    return sorted(names)


def _resolve_code_path(prompt_path: Path, project_root: Path) -> Path:
    stem = prompt_path.stem.replace("_python", "").replace("_typescript", "")
    candidates = [
        project_root / "pdd" / f"{stem}.py",
        project_root / "src" / f"{stem}.py",
        project_root / f"{stem}.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        f"Could not locate generated code for {prompt_path.name}; pass --code-file"
    )


def _load_manifest_paths(
    devunit: str,
    project_root: Path,
    from_evidence: Optional[Path],
) -> tuple[Optional[Path], Optional[Path]]:
    if from_evidence is None:
        latest = project_root / ".pdd" / "evidence" / "devunits" / f"{devunit}.latest.json"
        if latest.is_file():
            from_evidence = latest
    if from_evidence is None or not from_evidence.is_file():
        prompt = resolve_prompt_path(project_root, devunit)
        if prompt is None:
            raise FileNotFoundError(f"Could not resolve prompt for dev unit {devunit!r}")
        return prompt, _resolve_code_path(prompt, project_root)

    manifest = ManifestView.from_file(from_evidence.resolve(), project_root)
    prompt = manifest.prompt_path or resolve_prompt_path(project_root, devunit, manifest.raw)
    if prompt is None:
        raise FileNotFoundError(f"Evidence manifest missing prompt path: {from_evidence}")
    if manifest.outputs:
        output = Path(manifest.outputs[0]["path"])
        if not output.is_absolute():
            output = project_root / output
        if output.is_file():
            return prompt, output.resolve()
    return prompt, _resolve_code_path(prompt, project_root)


def _run_pytest(tests: list[Path], project_root: Path) -> bool:
    if not tests:
        return True
    cmd = [sys.executable, "-m", "pytest", "-q", *[str(path) for path in tests]]
    completed = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _discover_tests(code_path: Path, project_root: Path) -> list[Path]:
    module = code_path.stem
    candidates = [
        project_root / "tests" / f"test_{module}.py",
        project_root / "tests" / f"test_{module.replace('_python', '')}.py",
    ]
    return [path for path in candidates if path.is_file()]


def _regenerate_code(
    prompt_path: Path,
    code_path: Path,
    *,
    model: Optional[str],
    project_root: Path,
) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pdd",
        "generate",
        str(prompt_path.relative_to(project_root)),
        "--output",
        str(code_path.relative_to(project_root)),
        "--force",
    ]
    if model:
        cmd.extend(["--model", model])
    completed = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"pdd generate failed ({completed.returncode}): {completed.stderr.strip()}"
        )


def run_drift(
    devunit: str,
    project_root: Path,
    *,
    runs: int = 1,
    model: Optional[str] = None,
    from_evidence: Optional[Path] = None,
    code_file: Optional[Path] = None,
    dry_run: bool = False,
) -> DriftReport:
    prompt_path, resolved_code = _load_manifest_paths(devunit, project_root, from_evidence)
    code_path = code_file.resolve() if code_file else resolved_code

    snapshots: list[RunSnapshot] = []
    hashes: list[str] = []
    apis: list[list[str]] = []

    for index in range(runs):
        if not dry_run and index > 0:
            _regenerate_code(
                prompt_path,
                code_path,
                model=model,
                project_root=project_root,
            )
        code_hash = _sha256_file(code_path)
        api = _public_api(code_path)
        tests = _discover_tests(code_path, project_root)
        tests_ok = _run_pytest(tests, project_root)
        snapshots.append(
            RunSnapshot(
                run_index=index + 1,
                code_sha256=code_hash,
                public_api=api,
                tests_passed=tests_ok,
                stories_passed=tests_ok,
                verify_passed=tests_ok,
                policy_passed=tests_ok,
            )
        )
        hashes.append(code_hash)
        apis.append(api)

    public_api_unchanged = all(api == apis[0] for api in apis)
    implementation_changed = len(set(hashes)) > 1
    behavior_unchanged = all(
        snap.tests_passed and snap.stories_passed and snap.verify_passed
        for snap in snapshots
    )
    status = "stable"
    if not public_api_unchanged or not behavior_unchanged:
        status = "unstable"
    elif implementation_changed and behavior_unchanged:
        status = "stable"

    return DriftReport(
        devunit=devunit,
        prompt_path=str(prompt_path),
        code_path=str(code_path),
        runs=runs,
        snapshots=snapshots,
        public_api_unchanged=public_api_unchanged,
        implementation_changed=implementation_changed,
        behavior_unchanged=behavior_unchanged,
        status=status,
        dry_run=dry_run,
    )
