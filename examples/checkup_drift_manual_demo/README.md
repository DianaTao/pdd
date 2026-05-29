# `pdd checkup drift` — human verification demo (PR #1261)

Self-contained workspace to **manually verify** [`pdd checkup drift`](../../docs/drift.md) on branch **`feat/issue-831-drift`** without reading the implementation.

Related: [promptdriven/pdd#831](https://github.com/promptdriven/pdd/issues/831) · [PR #1261](https://github.com/promptdriven/pdd/pull/1261)

## What this demo covers

| Check | How you verify it here |
|-------|-------------------------|
| Non-mutating drift | Baseline file hash unchanged after `--dry-run` (see [RUN.md](RUN.md)) |
| Baseline API comparison | `--dry-run --json` reports `public_api_unchanged: true` |
| Evidence manifest (no false policy) | `--from-evidence` → `policy_check_skipped: true`, `status: stable` |
| Local imports + conftest | `refund_demo.helper` + `tests/conftest.py`; drift pytest path must pass |
| A0 → A1 prompts | Informal [A0](prompts/refund_payment_A0.prompt) vs formal [A1](prompts/refund_payment_A1.prompt); active prompt is [A1 copy](workspace/prompts/refund_payment_python.prompt) |

## Quick start

```bash
# From repo root on feat/issue-831-drift (or this demo branch)
conda activate pdd
pip install -e .

cd examples/checkup_drift_manual_demo
./run_demo.sh
```

Full steps and expected output: **[RUN.md](RUN.md)**  
Captured sample run: **[RESULTS.md](RESULTS.md)**

## Layout

```
checkup_drift_manual_demo/
├── README.md           ← you are here
├── RUN.md              ← human step-by-step instructions
├── RESULTS.md          ← expected + sample command output
├── run_demo.sh         ← offline-safe checks (no LLM)
├── prompts/
│   ├── refund_payment_A0.prompt   ← hand-crafted (informal)
│   └── refund_payment_A1.prompt   ← PDD-formalized (structured)
└── workspace/          ← mini project root (cd here for drift)
    ├── prompts/refund_payment_python.prompt  ← active A1 prompt
    ├── refund_demo/      ← baseline code + helper (local import; not named pdd/ — avoids CLI shadowing)
    ├── tests/            ← pytest + conftest fixture
    └── .pdd/evidence/    ← evidence manifest for --from-evidence
```

Optional LLM step (regeneration): see **Phase 2** in [RUN.md](RUN.md).
