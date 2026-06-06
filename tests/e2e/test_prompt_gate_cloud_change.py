"""Real-cloud E2E: ``pdd change`` through the PDD cloud backend, then the prompt gate.

This is the only test in the prompt-gate E2E set that makes a **real cloud call** —
nothing is stubbed. ``pdd change`` writes a ``.prompt`` whose content comes from the
cloud LLM (``change_func`` → ``llm_invoke`` → cloud endpoint), and the **real** prompt
gate then runs on it. ``PDD_CLOUD_ONLY`` disables local fallback, so a successful run
is genuine cloud execution.

Because it costs money and needs cloud auth, it is marked ``real``/``e2e`` (excluded
from the default CI selection) and **skips** unless cloud credentials are present.

Human-runnable::

    export PDD_JWT_TOKEN=<token>          # or device-flow creds (see tests/cloud_regression.sh)
    pytest -vv -m real tests/e2e/test_prompt_gate_cloud_change.py

It is deterministic in what it asserts (gate ran, prompt written, exit 0 in warn
mode) and tolerant of the model's exact wording.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_PATH = REPO_ROOT / "scripts" / "prompt_gate_e2e_demo.py"

_spec = importlib.util.spec_from_file_location("prompt_gate_e2e_demo", _DEMO_PATH)
assert _spec and _spec.loader
demo = importlib.util.module_from_spec(_spec)
sys.modules["prompt_gate_e2e_demo"] = demo
_spec.loader.exec_module(demo)

pytestmark = [pytest.mark.real, pytest.mark.e2e, pytest.mark.slow]


@pytest.mark.skipif(
    not demo.cloud_auth_available(),
    reason="no PDD cloud auth (set PDD_JWT_TOKEN or device-flow creds to run)",
)
def test_change_through_cloud_then_gate(tmp_path: Path) -> None:
    res = demo.run_change_cloud(tmp_path)
    assert not res.skipped, res.notes
    # warn mode → the run completes regardless of the cloud model's output.
    assert res.exit_code == 0, f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    # Substance: the cloud actually rewrote the prompt and the real gate ran on it.
    assert res.verified is True, res.notes
    assert "rewritten by cloud: True" in res.notes, res.notes
    assert "Prompt checkup" in res.stdout, res.stdout
