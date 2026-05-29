# Manual test plan — checkup gate demo

Branch: **`demo/checkup-gate-showcase`**. Related PRs: [#1260](https://github.com/promptdriven/pdd/pull/1260) (gate), [#1256](https://github.com/promptdriven/pdd/pull/1256) (evidence manifests).

## Prerequisites

```bash
git checkout demo/checkup-gate-showcase
cd examples/checkup_gate_demo
pip install -e "../..[dev]"
export PDD_SKIP_UPDATE_CHECK=1
export PDD_AUTO_UPDATE=false
```

If `pdd sync --help` lacks `--evidence`, remove stale `site-packages/pdd` and reinstall:

```bash
rm -rf ../../.venv/lib/python3.*/site-packages/pdd
pip install -e "../..[dev]"
```

## Tier 1 — Offline (no API keys)

| # | Command | Expected |
|---|---------|----------|
| 1 | `./run_offline_checks.sh` | Exit 0; pytest + offline scenarios + failed-sync gate demo |
| 2 | `./run_cli_smoke.sh` | Exit 0; `--evidence` on sync; no top-level `pdd gate` |
| 3 | `python ../../examples/checkup_gate_example.py` | Prints `All offline scenarios passed.` |
| 4 | `python demo_failed_sync_gate.py` | Exit 0; JSON `passed: false` with `stories_pass`, `verify_not_available`, `unit_tests_pass` |
| 5 | `pytest -vv ../../tests/test_checkup_gate_demo.py` | All tests green |

## Tier 2 — Live PDD (API keys via `pdd setup`)

Run only inside **`examples/checkup_gate_demo/`** (local `.pddrc` — not repo root).

| # | Command | Expected |
|---|---------|----------|
| 6 | `pdd sync refund --evidence` | Generates `src/`, `tests/`, `user_stories/`; writes `refund.latest.json` |
| 7 | `pdd checkup contract check prompts/` | 0 errors |
| 8 | `pdd checkup coverage prompts/` | Coverage table for R1–R3 |
| 9 | `pdd checkup gate refund --json` | See outcomes below |

### Gate outcomes after sync

| Sync result | Typical `passed` | Typical failure `code`s |
|-------------|------------------|------------------------|
| Sync **failed** (coverage/tests) | `false` | `stories_pass`, `verify_not_available`, `unit_tests_pass` |
| Sync **succeeded** | may still be `false` | `stories_pass` until `refund.latest.json` records `detect_stories` |

**Important:** `pdd detect --stories --evidence` writes **`stories.latest.json`**, not `refund.latest.json`. It does **not** clear `stories_pass` on `pdd checkup gate refund`. That is current product behavior (see `tests/test_checkup_gate_demo.py`).

### Permissive policy demo (offline manifest + live CLI)

After a successful sync with generated `src/refund.py`:

```bash
pdd checkup gate refund --json --policy .pdd/policy-permissive.yml
```

Relaxes `stories_pass` and contract-rule strictness for teaching policy overrides.

### Stale-output demo (after successful sync)

```bash
echo "# edit" >> src/refund.py
pdd checkup gate refund --json
# Expect failure code: stale_output
git checkout -- src/refund.py   # or re-sync
```

## Tier 3 — Full scripted live demo

```bash
CLEAN=1 ./run_demo.sh
```

Expect gate JSON `passed: true` only when sync fully succeeds **and** the refund manifest records passing validation for stories, verify, and unit tests.

## What to report on PR #1260 / #1256

- Exit codes for commands 6–9
- `failures[].code` from gate JSON
- Confirm only `prompts/refund_python.prompt` was hand-crafted
- Link to this branch: `demo/checkup-gate-showcase`
