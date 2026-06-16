"""Regression guards for DianaTao/pdd issue #10 — checkup findings.

Issue #10 is a checkup / code-review request. The earlier ``pdd checkup``
workflow surfaced several concrete static-analysis findings in
``DianaTao/pdd@main``. Each test below pins the **expected post-fix state**
for one of those findings so that:

* if the bug is still present at HEAD (as it is today), the test fails with
  a clear diagnostic, and
* if a future change re-introduces the same bug, the test fails again rather
  than silently regressing.

All checks are static / import-time / AST / ``importlib.metadata`` / Click
``CliRunner`` only — cheap CI tier, no network, no LLM calls, no auth.

Findings covered (see issue #10 Step 3/8 of the checkup workflow):

* S1 — ``pdd/server/click_executor.py:259`` uses ``List[str]`` in the
  ``_get_command_positional_args`` return annotation but never does
  ``from typing import List``. Because the file declares
  ``from __future__ import annotations`` (line 11), the annotation is stored
  as a string and the missing name only surfaces when
  ``typing.get_type_hints()`` resolves it — at which point a ``NameError``
  is raised.
* S2 — ``pdd/edit_file.py`` imports ``langgraph``, ``langchain``,
  ``langchain_core``, ``langchain_anthropic``, ``langchain_community`` and
  ``langchain_mcp_adapters`` at module top-level but none of those
  distributions are declared in ``pyproject.toml`` dependencies. The module
  is unimportable on a fresh install.
* S3 — eight bare ``except:`` clauses across ``pdd/`` swallow
  ``KeyboardInterrupt`` and ``SystemExit``.
* S4 — thirteen ``shell=True`` subprocess sites across ``pdd/``. We pin the
  inventory so any new additions are surfaced for review.
* S5 — manifest drift between ``pyproject.toml`` and ``requirements.txt``
  (e.g. ``litellm`` ceiling, ``keyring`` missing from requirements).

Plus two CLI smoke tests confirming the public entry point still loads.
"""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import re
import subprocess
import sys
import typing
from pathlib import Path

import pytest
from click.testing import CliRunner


# --- locate repo root relative to this test file so the tests work
# regardless of the working directory pytest is invoked from.
REPO_ROOT = Path(__file__).resolve().parents[1]
PDD_DIR = REPO_ROOT / "pdd"
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"


# --------------------------------------------------------------------------- #
# Scenario S1: click_executor.py — missing ``from typing import List`` import
# --------------------------------------------------------------------------- #


class TestClickExecutorListImport:
    """Regression guard for the missing ``List`` import in click_executor."""

    CLICK_EXECUTOR = PDD_DIR / "server" / "click_executor.py"

    def test_click_executor_file_exists(self) -> None:
        """Sanity check — the file under audit is present."""
        assert self.CLICK_EXECUTOR.is_file(), (
            f"Expected {self.CLICK_EXECUTOR} to exist; the test plan from "
            f"issue #10 targets this file."
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Known bug from issue #10 checkup: pdd/server/click_executor.py "
            "uses ``List[str]`` in a return annotation but does not import "
            "``List`` from ``typing``. Awaiting fix from the pdd-fix workflow. "
            "Once the fix lands, this test will pass and the xfail will be "
            "reported as XPASS — that's the signal to remove the marker."
        ),
    )
    def test_list_is_imported_from_typing(self) -> None:
        """``List`` must be imported from ``typing`` (or aliased) at module top.

        Static AST walk — does not execute the module. We accept either:

        * ``from typing import ..., List, ...`` (any position in the list), or
        * ``import typing`` + use of ``typing.List`` in the file.

        Either form satisfies ``typing.get_type_hints()`` resolution.
        """
        source = self.CLICK_EXECUTOR.read_text()
        tree = ast.parse(source)

        imported_names: set[str] = set()
        typing_module_imported = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "typing":
                        typing_module_imported = True

        # Accept either ``from typing import List`` style or qualified usage
        # via ``typing.List`` (in which case ``typing`` must be imported).
        has_unqualified_import = "List" in imported_names
        uses_qualified_list = (
            typing_module_imported and "typing.List" in source
        )

        assert has_unqualified_import or uses_qualified_list, (
            "pdd/server/click_executor.py uses ``List[str]`` in the return "
            "annotation of ``_get_command_positional_args`` (line 259) but "
            "does not import ``List`` from ``typing``. With "
            "``from __future__ import annotations`` (line 11) active, the "
            "annotation is stored as a string; any call to "
            "``typing.get_type_hints()`` on this function raises NameError. "
            "Fix: add ``List`` to the ``from typing import ...`` line."
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Known bug from issue #10 checkup: missing ``from typing import "
            "List`` causes typing.get_type_hints() to raise NameError. "
            "Awaiting fix from the pdd-fix workflow."
        ),
    )
    def test_get_type_hints_resolves_for_command_positional_args(self) -> None:
        """``typing.get_type_hints`` on the function must succeed.

        This is the runtime symptom that the missing import causes. Once
        ``List`` is imported, this call returns ``{'return': List[str], ...}``.
        Until then it raises ``NameError: name 'List' is not defined``.
        """
        mod = importlib.import_module("pdd.server.click_executor")
        func = getattr(mod, "_get_command_positional_args", None)
        assert func is not None, (
            "pdd.server.click_executor._get_command_positional_args is "
            "missing — has the function been renamed or removed?"
        )

        try:
            hints = typing.get_type_hints(func)
        except NameError as exc:  # pragma: no cover - failure-mode assertion
            pytest.fail(
                "typing.get_type_hints(_get_command_positional_args) raised "
                f"NameError: {exc}. This confirms the missing ``from typing "
                f"import List`` in pdd/server/click_executor.py. Fix: add "
                f"``List`` to the typing import on line 17."
            )

        assert "return" in hints, (
            "Expected a resolved 'return' annotation after fixing the import."
        )


# --------------------------------------------------------------------------- #
# Scenario S2: edit_file.py — undeclared langchain/langgraph dependencies
# --------------------------------------------------------------------------- #


# (top-level import name, expected PyPI distribution name)
LANGCHAIN_IMPORTS: tuple[tuple[str, str], ...] = (
    ("langgraph", "langgraph"),
    ("langchain", "langchain"),
    ("langchain_core", "langchain-core"),
    ("langchain_anthropic", "langchain-anthropic"),
    ("langchain_community", "langchain-community"),
    ("langchain_mcp_adapters", "langchain-mcp-adapters"),
)


def _read_pyproject_text() -> str:
    assert PYPROJECT.is_file(), f"pyproject.toml not found at {PYPROJECT}"
    return PYPROJECT.read_text()


class TestEditFileLangchainDependencies:
    """Regression guard for ``pdd/edit_file.py`` undeclared deps."""

    EDIT_FILE = PDD_DIR / "edit_file.py"

    def test_edit_file_module_present(self) -> None:
        assert self.EDIT_FILE.is_file(), (
            f"Expected {self.EDIT_FILE} to exist; the langchain-deps finding "
            f"targets this file."
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Known bug from issue #10 checkup: pdd/edit_file.py imports "
            "langgraph / langchain* without those distributions being "
            "declared in pyproject.toml or requirements.txt. Awaiting fix "
            "from the pdd-fix workflow."
        ),
    )
    @pytest.mark.parametrize("top_level,distribution", LANGCHAIN_IMPORTS)
    def test_imported_distribution_is_declared(
        self, top_level: str, distribution: str
    ) -> None:
        """Every top-level langchain import must have a matching declaration.

        We accept the dependency being declared in any of:

        * ``[project].dependencies`` in pyproject.toml,
        * ``[project.optional-dependencies]`` in pyproject.toml, or
        * ``requirements.txt``.

        We also accept it being declared with a marker string such as
        ``langgraph>=0.2`` — the match is a case-insensitive substring of
        the distribution name on the same line.
        """
        # Confirm the module actually imports the package (or the bug is
        # already half-fixed by removing the import).
        source = self.EDIT_FILE.read_text()
        tree = ast.parse(source)
        top_imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_imports.add(node.module.split(".")[0])

        if top_level not in top_imports:
            pytest.skip(
                f"{top_level} is no longer imported by pdd/edit_file.py — "
                f"the bug was fixed by removing the import. Drop this "
                f"distribution from the parametrize tuple to clean up."
            )

        pyproject = _read_pyproject_text().lower()
        # ``-`` and ``_`` are both legal separators in distribution names; the
        # PyPI canonical form uses ``-``. We probe both spellings to avoid
        # false negatives.
        candidates = {distribution.lower(), distribution.lower().replace("-", "_")}

        declared_in_pyproject = any(c in pyproject for c in candidates)

        declared_in_requirements = False
        if REQUIREMENTS.is_file():
            req_text = REQUIREMENTS.read_text().lower()
            declared_in_requirements = any(c in req_text for c in candidates)

        assert declared_in_pyproject or declared_in_requirements, (
            f"pdd/edit_file.py imports ``{top_level}`` but the corresponding "
            f"distribution ``{distribution}`` is not declared in "
            f"pyproject.toml or requirements.txt. Fresh installs will fail "
            f"with ModuleNotFoundError at ``import pdd.edit_file``. "
            f"Fix: either add ``{distribution}`` to "
            f"``[project].dependencies`` in pyproject.toml, or guard the "
            f"import behind a try/except and raise a helpful ImportError "
            f"when the optional feature is used."
        )

    def test_edit_file_is_importable_on_clean_install(self) -> None:
        """End-to-end check: ``import pdd.edit_file`` must succeed.

        Skips (does not fail) if any langchain distribution is missing on
        the current interpreter — the per-distribution test above is the
        authoritative manifest gate; this one only fires when the deps are
        nominally installed so we catch other import-time regressions.
        """
        try:
            for top_level, _ in LANGCHAIN_IMPORTS:
                importlib.import_module(top_level)
        except ImportError as exc:
            pytest.skip(
                f"langchain stack not installed in this environment "
                f"({exc}); manifest-level test enforces declaration. "
                f"Install the langchain stack to run this end-to-end check."
            )

        # All langchain deps importable — pdd.edit_file should be too.
        try:
            importlib.import_module("pdd.edit_file")
        except ImportError as exc:  # pragma: no cover - failure-mode assertion
            pytest.fail(
                f"import pdd.edit_file failed even though langchain deps are "
                f"available: {exc}"
            )


# --------------------------------------------------------------------------- #
# Scenario S3: bare ``except:`` clauses
# --------------------------------------------------------------------------- #


def _walk_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _find_bare_excepts(path: Path) -> list[int]:
    """Return line numbers (1-indexed) of bare ``except:`` clauses.

    Uses AST so we don't false-match on strings, comments, or commented-out
    code. A bare ``except`` is an ``ast.ExceptHandler`` with ``type is None``.
    """
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:  # pragma: no cover - tests/ stays syntactically valid
        return []
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.type is None
    ]


class TestNoBareExcepts:
    """Regression guard for bare ``except:`` clauses under ``pdd/``.

    Uses the same baseline-inventory pattern as the ``shell=True`` test
    (S4): pin the current set of offenders, then fail if the count grows
    or new files start using bare ``except:``. Decreasing is welcome (and
    silently passes); the per-file baseline should be edited down (or to
    ``0``) as fixes land.
    """

    # Baseline inventory at the time of the issue #10 checkup. Each entry is
    # the count of bare ``except:`` clauses in that file. The S3 finding is
    # that all of these should eventually drop to zero; until the pdd-fix
    # workflow lands, this test pins the current state so any new bare
    # except *anywhere* fails CI.
    EXPECTED_BARE_EXCEPT_SITES: dict[str, int] = {
        "pdd/agentic_common.py": 1,
        "pdd/construct_paths.py": 1,
        "pdd/fix_errors_from_unit_tests.py": 2,
        "pdd/pin_example_hack.py": 1,
        "pdd/sync_orchestration.py": 1,
        "pdd/unfinished_prompt.py": 1,
        "pdd/update_main.py": 1,
    }
    EXPECTED_BARE_EXCEPT_TOTAL = sum(EXPECTED_BARE_EXCEPT_SITES.values())

    def test_pdd_directory_exists(self) -> None:
        assert PDD_DIR.is_dir(), f"Expected {PDD_DIR} to exist."

    def test_bare_except_inventory_does_not_grow(self) -> None:
        """Bare ``except:`` count in ``pdd/`` must not exceed the baseline.

        Decreasing is welcome — fixing one is a one-line edit and the test
        will still pass. Adding new sites without updating the baseline
        above forces the change author to justify the addition.

        Bare excepts swallow ``KeyboardInterrupt`` and ``SystemExit`` and
        mask programming errors. Replace with ``except Exception:`` (or a
        narrower base class) before catching anything you didn't anticipate.
        """
        per_file: dict[str, int] = {}
        total = 0
        for path in _walk_python_files(PDD_DIR):
            lines = _find_bare_excepts(path)
            if lines:
                rel = path.relative_to(REPO_ROOT).as_posix()
                per_file[rel] = len(lines)
                total += len(lines)

        # Files exceeding their baseline (i.e. new bare excepts added).
        regressions = {
            rel: count
            for rel, count in per_file.items()
            if count > self.EXPECTED_BARE_EXCEPT_SITES.get(rel, 0)
        }

        if regressions or total > self.EXPECTED_BARE_EXCEPT_TOTAL:
            details = "\n".join(
                f"  - {rel}: {count} "
                f"(baseline {self.EXPECTED_BARE_EXCEPT_SITES.get(rel, 0)})"
                for rel, count in sorted(per_file.items())
            )
            pytest.fail(
                f"Bare ``except:`` count grew from "
                f"{self.EXPECTED_BARE_EXCEPT_TOTAL} to {total} in pdd/:\n"
                + details
                + "\n\nReplace each new occurrence with ``except Exception:`` "
                "or a narrower base class. If the addition is intentional, "
                "update EXPECTED_BARE_EXCEPT_SITES with justification."
            )

    def test_no_new_files_introduce_bare_excepts(self) -> None:
        """No new file under ``pdd/`` may add a bare ``except:`` clause."""
        unexpected: dict[str, int] = {}
        for path in _walk_python_files(PDD_DIR):
            lines = _find_bare_excepts(path)
            if not lines:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel not in self.EXPECTED_BARE_EXCEPT_SITES:
                unexpected[rel] = len(lines)

        assert not unexpected, (
            "New file(s) introduced bare ``except:`` clauses without "
            "updating the baseline inventory:\n"
            + "\n".join(f"  - {rel}: {n}" for rel, n in sorted(unexpected.items()))
            + "\n\nReplace with ``except Exception:`` or the specific "
            "exception type you mean to catch."
        )


# --------------------------------------------------------------------------- #
# Scenario S4: ``shell=True`` subprocess inventory
# --------------------------------------------------------------------------- #


# Expected inventory at the time of the checkup. The point of this test is
# not to forbid ``shell=True`` outright (verification commands sometimes
# legitimately need shell features like piping) but to *gate additions*
# behind a deliberate review: any new occurrence forces an update of this
# baseline.
EXPECTED_SHELL_TRUE_SITES: dict[str, int] = {
    "pdd/agentic_sync.py": 1,
    "pdd/agentic_crash.py": 1,
    "pdd/cli_detector.py": 1,
    "pdd/auto_update.py": 2,
    "pdd/fix_error_loop.py": 1,
    "pdd/fix_code_loop.py": 1,
    "pdd/fix_verification_errors_loop.py": 1,
    "pdd/sync_orchestration.py": 2,
    "pdd/preprocess.py": 1,
    "pdd/pin_example_hack.py": 2,
}
EXPECTED_SHELL_TRUE_TOTAL = sum(EXPECTED_SHELL_TRUE_SITES.values())  # 13


def _count_shell_true_calls(path: Path) -> int:
    """Count subprocess calls passing ``shell=True``.

    Uses AST: counts ``ast.keyword`` nodes named ``shell`` whose value is the
    constant ``True``. This avoids matching ``shell=True`` in strings or
    comments.
    """
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:  # pragma: no cover
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    count += 1
    return count


class TestShellTrueInventory:
    """Regression guard for ``shell=True`` subprocess inventory."""

    def test_shell_true_total_matches_baseline(self) -> None:
        """Total ``shell=True`` usages must not grow above the baseline.

        Decreasing is fine (a fix). Adding new sites without updating the
        baseline above forces the change author to justify the addition.
        """
        total = 0
        per_file: dict[str, int] = {}
        for path in _walk_python_files(PDD_DIR):
            n = _count_shell_true_calls(path)
            if n:
                rel = path.relative_to(REPO_ROOT).as_posix()
                per_file[rel] = n
                total += n

        assert total <= EXPECTED_SHELL_TRUE_TOTAL, (
            f"shell=True usage in pdd/ grew from {EXPECTED_SHELL_TRUE_TOTAL} "
            f"to {total}. New sites:\n"
            + "\n".join(
                f"  - {rel}: {per_file.get(rel, 0)} "
                f"(baseline {EXPECTED_SHELL_TRUE_SITES.get(rel, 0)})"
                for rel in sorted(per_file)
                if per_file.get(rel, 0) > EXPECTED_SHELL_TRUE_SITES.get(rel, 0)
            )
            + "\n\nIf the addition is intentional, update "
            "EXPECTED_SHELL_TRUE_SITES with a code-review note explaining "
            "why ``shell=False`` (list-form argv) is not sufficient."
        )

    def test_shell_true_inventory_does_not_include_unexpected_files(self) -> None:
        """No new file may start using ``shell=True`` without baseline edit."""
        unexpected: dict[str, int] = {}
        for path in _walk_python_files(PDD_DIR):
            n = _count_shell_true_calls(path)
            if not n:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel not in EXPECTED_SHELL_TRUE_SITES:
                unexpected[rel] = n

        assert not unexpected, (
            "New file(s) introduced shell=True without updating the "
            f"baseline inventory:\n"
            + "\n".join(f"  - {rel}: {n}" for rel, n in sorted(unexpected.items()))
            + "\n\nAdd these to EXPECTED_SHELL_TRUE_SITES with a comment "
            "documenting why shell=True is required."
        )


# --------------------------------------------------------------------------- #
# Scenario S5: manifest drift between pyproject.toml and requirements.txt
# --------------------------------------------------------------------------- #


def _pin_line(text: str, distribution: str) -> str | None:
    """Return the first line in *text* that pins *distribution*, or None.

    Match is case-insensitive on the distribution name at line start (after
    any leading whitespace and stripping any extras suffix).
    """
    # Allow an optional leading quote so we match both ``requirements.txt``
    # form (``keyring==25.6.0``) and ``pyproject.toml`` array form
    # (``    "keyring==25.6.0",``).
    pattern = re.compile(
        rf"^\s*[\"']?{re.escape(distribution)}(\[[^\]]+\])?\s*(==|>=|<=|<|>|~=)",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        if pattern.match(line):
            return line.strip()
    return None


class TestManifestConsistency:
    """Regression guard for pyproject.toml vs requirements.txt drift."""

    def test_pyproject_exists(self) -> None:
        assert PYPROJECT.is_file(), f"pyproject.toml missing at {PYPROJECT}"

    def test_requirements_exists(self) -> None:
        if not REQUIREMENTS.is_file():
            pytest.skip(
                "requirements.txt is not present in this checkout — drift "
                "test is vacuously satisfied. If you intentionally removed "
                "requirements.txt, update this test to no longer skip."
            )
        assert REQUIREMENTS.is_file()

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Known drift from issue #10 checkup: pyproject.toml pins "
            "``litellm[caching]>=1.80.0,<=1.82.6`` while requirements.txt "
            "drops the ``<=`` ceiling. Awaiting fix from the pdd-fix workflow."
        ),
    )
    def test_litellm_pin_matches_between_manifests(self) -> None:
        """``litellm`` ceiling in pyproject must also appear in requirements.

        Step 2 of the checkup flagged that pyproject.toml pins
        ``litellm[caching]>=1.80.0,<=1.82.6`` while requirements.txt drops
        the ``<=`` ceiling — two install paths can resolve to different
        versions.
        """
        if not REQUIREMENTS.is_file():
            pytest.skip("requirements.txt not present")

        pyproject_line = _pin_line(_read_pyproject_text(), "litellm")
        requirements_line = _pin_line(REQUIREMENTS.read_text(), "litellm")

        if pyproject_line is None or requirements_line is None:
            pytest.skip(
                f"litellm not pinned in one of the manifests "
                f"(pyproject={pyproject_line!r}, requirements={requirements_line!r})."
            )

        # Normalize whitespace and case for comparison.
        norm_py = re.sub(r"\s+", "", pyproject_line.lower())
        norm_req = re.sub(r"\s+", "", requirements_line.lower())

        assert norm_py == norm_req, (
            "litellm pin disagrees between manifests:\n"
            f"  pyproject.toml:   {pyproject_line}\n"
            f"  requirements.txt: {requirements_line}\n"
            "Pick pyproject.toml as the source of truth and regenerate "
            "requirements.txt (e.g. with ``pip-compile``)."
        )

    def test_keyring_declared_in_both_manifests(self) -> None:
        """``keyring`` must appear in both manifests or neither.

        Step 2 flagged that pyproject.toml declares ``keyring==25.6.0`` but
        requirements.txt omits it. Production installs that follow
        requirements.txt then lack a runtime dependency.
        """
        if not REQUIREMENTS.is_file():
            pytest.skip("requirements.txt not present")

        py_has = _pin_line(_read_pyproject_text(), "keyring") is not None
        req_has = _pin_line(REQUIREMENTS.read_text(), "keyring") is not None

        assert py_has == req_has, (
            "keyring declaration is asymmetric between manifests "
            f"(pyproject={py_has}, requirements.txt={req_has}). "
            "Either declare it in both or remove from both."
        )


# --------------------------------------------------------------------------- #
# Smoke tests — public CLI entry point still loads
# --------------------------------------------------------------------------- #


class TestCliSmoke:
    """Two cheap smoke tests on the public CLI surface.

    These run in <1s, don't need network/auth, and catch the worst classes of
    regression: import-time failures and broken ``--help`` output.
    """

    def test_pdd_cli_help_via_runner(self) -> None:
        """``CliRunner`` invocation of the root ``cli`` command succeeds."""
        from pdd.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0, (
            f"`pdd --help` (via CliRunner) exited {result.exit_code}.\n"
            f"stdout:\n{result.stdout}\n"
            f"exception: {result.exception!r}"
        )
        assert "Usage" in result.stdout or "usage" in result.stdout, (
            "`pdd --help` output did not contain a usage banner; "
            "Click may have failed before reaching the help formatter."
        )

    def test_pdd_cli_help_via_subprocess(self) -> None:
        """``python -m pdd --help`` works as a subprocess entry point.

        This catches regressions that ``CliRunner`` masks — e.g. issues with
        ``__main__.py`` wiring, side-effect-only imports, or sys.path setup.
        """
        result = subprocess.run(
            [sys.executable, "-m", "pdd", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"`python -m pdd --help` exited {result.returncode}.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        combined = (result.stdout + result.stderr).lower()
        assert "usage" in combined, (
            "subprocess `python -m pdd --help` did not contain a usage "
            "banner in stdout or stderr."
        )
