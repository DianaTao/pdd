# Sample results — manual drift demo

Captured on **`feat/issue-831-drift-manual-demo`** with `run_demo.sh` (Phase 1, offline).

Environment: `conda activate pdd`, `pip install -e .` from repo root, `PDD_SKIP_UPDATE_CHECK=1`.

## 1. Baseline pytest

```
..                                                                       [100%]
2 passed in 0.03s
```

## 2. `pdd checkup drift refund_payment --dry-run --json`

Command:

```bash
cd examples/checkup_drift_manual_demo/workspace
python -m pdd checkup drift refund_payment \
  --code-file refund_demo/refund_payment.py \
  --dry-run --json
```

Key fields (expected):

```json
{
  "status": "stable",
  "dry_run": true,
  "public_api_unchanged": true,
  "behavior_unchanged": true,
  "policy_check_skipped": true,
  "policy_check_unavailable": false,
  "tests": "passed 1/1",
  "snapshots": [
    {
      "tests_passed": true,
      "public_api": ["def refund_payment"]
    }
  ]
}
```

## 3. `--from-evidence` (ordinary manifest, no policy file)

Command:

```bash
python -m pdd checkup drift refund_payment \
  --from-evidence .pdd/evidence/devunits/refund_payment.latest.json \
  --code-file refund_demo/refund_payment.py \
  --dry-run --json
```

Key fields (expected):

```json
{
  "status": "stable",
  "policy_check_skipped": true,
  "policy_check_unavailable": false
}
```

## 4. Worktree unchanged

```
OK: baseline file hash unchanged (2ffbc6dfeb9f5b840acdc25f1c59911ad576a5aaf2ffce75c6042a0327106125)
```

## 5. No top-level `pdd drift`

```bash
python -m pdd --help | grep -E '^  drift'   # should print nothing
python -m pdd checkup --help                # documents drift subcommand
```

## A0 vs A1 prompt diff (summary)

| Aspect | A0 (hand-crafted) | A1 (PDD-formalized) |
|--------|-------------------|---------------------|
| Structure | Plain prose bullets | `<pdd-reason>`, `<pdd-interface>` JSON |
| Paths | `refund_demo/...` | Same, explicit interface contract |
| Use | Human baseline spec | Generation + drift active prompt |

Full files: [prompts/refund_payment_A0.prompt](prompts/refund_payment_A0.prompt), [prompts/refund_payment_A1.prompt](prompts/refund_payment_A1.prompt).

## Automated equivalent

CI covers the same behaviors in:

- `tests/test_drift_main.py`
- `tests/commands/test_drift_cli.py`

This demo is for **human replay** when reviewing [PR #1261](https://github.com/promptdriven/pdd/pull/1261).
