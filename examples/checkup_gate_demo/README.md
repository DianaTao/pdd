# Checkup gate demo — `refund` dev unit

**Hand-crafted source:** `prompts/refund_python.prompt` only.

**Generated (do not commit):** `src/`, `tests/`, `examples/`, `user_stories/`, `.pdd/`
— produced by `pdd sync refund --evidence`.

Requires branch `demo/checkup-gate-showcase` (or gate PR #1260).

## Quick start

```bash
cd examples/checkup_gate_demo
export PDD_FORCE=1
pip install -e "../..[dev]"    # must be repo install — PyPI pdd-cli may lack --evidence
pdd setup

pdd sync --help | grep evidence   # must show --evidence
./run_demo.sh
```

### Troubleshooting “no evidence”

| Symptom | Cause | Fix |
|---------|--------|-----|
| `No such option '--evidence'` | PyPI / wrong `pdd` on PATH | `pip install -e "../..[dev]"`, `which pdd` |
| No `.pdd/evidence/…` after sync | Sync failed or ran without `--evidence` | Re-run `pdd sync refund --evidence`; check exit code |
| Wrong directory | Evidence writes to **cwd** | Run commands inside `examples/checkup_gate_demo/` |
| Upgrade prompt reinstalled PyPI | Answered `y` to upgrade | `export PDD_FORCE=1` and editable reinstall |

Regenerate from a clean tree:

```bash
CLEAN=1 ./run_demo.sh
```

## Commands

```bash
pdd sync refund --evidence
pdd checkup contract check prompts/
pdd checkup coverage prompts/
pdd checkup gate refund --json
```

## Human-runnable tests (no API)

```bash
./run_cli_smoke.sh          # --evidence on sync; gate under checkup; cwd layout
./run_offline_checks.sh     # pytest + offline scenarios + failed-sync gate demo
python demo_failed_sync_gate.py   # same failure codes as a failed sync run
```

Full checklist: [MANUAL_TESTS.md](MANUAL_TESTS.md).

**Captured live output:** [VALIDATION_CAPTURE.md](VALIDATION_CAPTURE.md) (PR audit trail).

**Note:** `pdd detect --stories --evidence` writes `stories.latest.json`, not
`refund.latest.json`, so it does not satisfy `stories_pass` on
`pdd checkup gate refund` until sync records stories on the refund manifest.

## Agent prompt

`agent.prompt` — copy-paste instructions for coding agents.

## Offline gate engine demo (no API)

Does not run sync; exercises policy logic only:

```bash
./run_offline_checks.sh
# or: python ../../examples/checkup_gate_example.py
```

See [docs/checkup_gate_demo.md](../../docs/checkup_gate_demo.md).
