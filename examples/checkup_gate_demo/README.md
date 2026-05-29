# `pdd checkup gate` demo fixture

Offline-friendly assets for demonstrating the **evidence policy gate** introduced in
[PR #1260](https://github.com/promptdriven/pdd/pull/1260) (issue [#833](https://github.com/promptdriven/pdd/issues/833)).

This is **not** the PR review-loop deterministic gates (`pdd checkup --no-gates`).

## Quick start

From the repository root (on branch `demo/checkup-gate-showcase` or `feat/issue-825-gate`):

```bash
export PDD_FORCE=1
pip install -e ".[dev]"

# Automated walkthrough (no LLM, uses gate engine directly)
python examples/checkup_gate_example.py

# Manual CLI against this fixture tree
cd examples/checkup_gate_demo
pdd checkup gate refund --json
```

## Layout

| Path | Purpose |
|------|---------|
| `src/refund.py` | Generated-output stand-in |
| `prompts/refund_demo_python.prompt` | Prompt path referenced by demo manifests |
| `.pdd/policy-permissive.yml` | Sample policy allowing skip-shaped validation |
| `manifests.py` | Helper to write schema-v1 evidence JSON |
| `agent.prompt` | Copy-paste task prompt for coding agents |

## Typical demo sequence

1. `pdd checkup gate` in an empty temp dir → `no_manifests`
2. Run `checkup_gate_example.py` → prints pass/fail for each scenario
3. Edit `src/refund.py` → `pdd checkup gate refund` → `stale_output`
4. `pdd checkup gate --policy .pdd/policy-permissive.yml` with skip-shaped manifest

See [docs/checkup_gate_demo.md](../../docs/checkup_gate_demo.md) for full commands.
