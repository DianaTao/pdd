# Manual verification runbook — `pdd checkup drift`

Use this after checking out **`feat/issue-831-drift`** (or branch **`feat/issue-831-drift-manual-demo`**) and installing the CLI from the repo.

Related: [PR #1261](https://github.com/promptdriven/pdd/pull/1261)

## Prerequisites

```bash
conda activate pdd
cd /path/to/pdd   # repo root
pip install -e .
export PDD_SKIP_UPDATE_CHECK=1   # optional: skip version nag
```

## Prompts (A0 hand-crafted vs A1 formalized)

| File | Role |
|------|------|
| [prompts/refund_payment_A0.prompt](prompts/refund_payment_A0.prompt) | **A0** — informal, human-written baseline spec |
| [prompts/refund_payment_A1.prompt](prompts/refund_payment_A1.prompt) | **A1** — PDD-formalized prompt (`<pdd-interface>`, structured requirements) |
| [workspace/prompts/refund_payment_python.prompt](workspace/prompts/refund_payment_python.prompt) | **Active** copy of A1 used by drift in this demo |

Compare A0 vs A1 side by side to see formalization; drift uses the A1 copy as the generation source of truth.

## Phase 1 — Offline checks (no LLM)

From repo root:

```bash
./examples/checkup_drift_manual_demo/run_demo.sh
```

Or step by step:

```bash
cd examples/checkup_drift_manual_demo/workspace
rm -rf pdd   # IMPORTANT: never keep a workspace/pdd/ folder — it shadows the CLI

python -m pytest -q tests/test_refund_payment.py

python -m pdd checkup drift refund_payment \
  --code-file refund_demo/refund_payment.py \
  --dry-run --json

python -m pdd checkup drift refund_payment \
  --from-evidence .pdd/evidence/devunits/refund_payment.latest.json \
  --code-file refund_demo/refund_payment.py \
  --dry-run --json

shasum -a 256 refund_demo/refund_payment.py   # note hash before/after — must match
```

### What you should see

- Pytest: **2 passed**
- Dry-run JSON: `"status": "stable"`, `"public_api_unchanged": true`
- Evidence JSON: `"policy_check_skipped": true`, `"policy_check_unavailable": false`
- Baseline file **unchanged** after drift

Sample captured output: [RESULTS.md](RESULTS.md)

## Phase 2 — Optional regeneration (LLM / API key)

Requires `pdd setup` credentials and spend (default max budget $20).

```bash
cd examples/checkup_drift_manual_demo/workspace
rm -rf pdd

python -m pdd checkup drift refund_payment \
  --code-file refund_demo/refund_payment.py \
  --runs 1 \
  --max-cost 5 \
  --json
```

Verify again:

```bash
shasum -a 256 refund_demo/refund_payment.py
```

The worktree baseline file must remain byte-identical; regeneration happens under temp `candidates/` paths only.

## Phase 3 — Human checks for reviewer concerns

| Concern | How to verify manually |
|---------|-------------------------|
| Local import (`refund_demo.helper`) | Phase 1 pytest + drift `tests_passed: true` |
| `conftest.py` fixture | `tests/conftest.py` defines `fee`; both pytest tests pass |
| Evidence without policy gate | Phase 1 step 3 JSON |
| No top-level `pdd drift` | `python -m pdd --help` — lists `checkup`, not `drift` at top level |
| A0 → A1 workflow | Diff the two prompts; optional `pdd generate` from A1 with `--output /tmp/candidate.py` |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ImportError: cannot import name 'get_version' from 'pdd'` | Remove `workspace/pdd/` (empty dir shadows CLI). Use `refund_demo/` package name. |
| Upgrade prompt blocks script | `export PDD_SKIP_UPDATE_CHECK=1` and use `python -m pdd`, not an old global `pdd` binary. |
| Drift cannot find code | Pass `--code-file refund_demo/refund_payment.py`. |
