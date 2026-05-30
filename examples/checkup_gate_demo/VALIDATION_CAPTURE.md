# Live validation capture — checkup gate demo

Auditable output for PR [#1260](https://github.com/promptdriven/pdd/pull/1260) /
evidence [#1256](https://github.com/promptdriven/pdd/pull/1256).

**Branch:** `demo/checkup-gate-showcase` (`15cc1eaab` + rerun fixes)  
**Captured:** 2026-05-30 (isolated worktree `/tmp/pdd-gate-demo`)  
**Environment:** macOS, Python 3.13, `pdd` 0.0.255.dev0 (editable), `CI=1`, `PDD_SKIP_UPDATE_CHECK=1`

## Commands and exit codes (re-run with fixes)

| Step | Command | Exit code | Notes |
|------|---------|-----------|-------|
| Offline | `./run_offline_checks.sh` | **0** | 31 pytest passed (incl. `test_gate_failed_sync.py`) |
| Live full | `CLEAN=1 ./run_demo.sh` | **0** | All 4 steps complete (see below) |
| Live sync | `pdd sync refund --evidence` | **1** | Failed: coverage 0.0% below target 90.0% |
| Live contract | `pdd checkup contract check prompts/` | **0** | 0 errors |
| Live coverage | `pdd checkup coverage prompts/` | **1** | 2/3 checked; exits 1 for test-only R3 (advisory) |
| Live gate | `pdd checkup gate refund --json` | **1** | `passed: false` (see JSON below) |

## Live sync summary (step 1)

```
Overall status: Failed
Details: Sync failed: Coverage 0.0% below target 90.0% after 2 test_extend attempts
Total time: 68.06s | Total cost: $0.6464
Evidence manifest: .pdd/evidence/devunits/refund.latest.json
```

Manifest validation recorded:

```json
{
  "detect_stories": "not_applicable",
  "unit_tests": "failed",
  "verify": "not_available"
}
```

## Live gate JSON (`pdd checkup gate refund --json`)

**Exit code: 1**

```json
{
  "passed": false,
  "exit_code": 1,
  "manifests_checked": 1,
  "failures": [
    {"code": "stories_pass"},
    {"code": "verify_not_available"},
    {"code": "unit_tests_pass"}
  ]
}
```

**`failures[].code`:** `stories_pass`, `verify_not_available`, `unit_tests_pass`

Full JSON (same as prior capture):

```json
{
  "passed": false,
  "exit_code": 1,
  "manifests_checked": 1,
  "policy": {
    "require": {
      "stories_pass": true,
      "verify_pass": true,
      "unit_tests_pass": true,
      "generated_outputs_fresh": true,
      "no_unchecked_critical_rules": true
    },
    "allow": {
      "waivers": true,
      "story_only_rules": false,
      "skipped_verify": false,
      "skipped_tests": false
    },
    "limits": {
      "max_cost_usd": 20.0,
      "max_nondeterministic_context_items": 0
    },
    "path": null
  },
  "failures": [
    {
      "code": "stories_pass",
      "message": "refund: validation.detect_stories is 'not_applicable' but policy requires stories_pass",
      "fix_command": "pdd detect --stories"
    },
    {
      "code": "verify_not_available",
      "message": "refund: validation.verify is not_available (required check was not recorded)",
      "fix_command": "Run a PDD command with --evidence for refund"
    },
    {
      "code": "unit_tests_pass",
      "message": "refund: validation.unit_tests='failed'",
      "fix_command": "pytest <tests>"
    }
  ]
}
```

## Fixes applied before this re-run

1. **`validation_from_sync`** — prefer per-language `success` over stale top-level `overall_success`.
2. **`pdd sync --evidence`** — write failure manifest when `sync_main` raises (prevents stale pass manifest).
3. **`run_demo.sh`** — continue through coverage exit 1 and failed sync to always reach gate step.

Regression: `tests/test_gate_failed_sync.py` (7 tests).

## Debug notes: can gate pass after failed sync?

| Scenario | Gate `passed` under default policy? | Status |
|----------|-------------------------------------|--------|
| Normal failed sync writes fresh manifest | **false** | Working as designed (this capture) |
| Stale manifest + sync throws before evidence write | **true** (was bug) | **Fixed** — exception path writes manifest |
| Inconsistent `overall_success: true` + lang `success: false` | could mark tests passed (was bug) | **Fixed** — per-language outcomes win |

## Reproduce

```bash
git fetch fork demo/checkup-gate-showcase
git worktree add /tmp/pdd-gate-demo fork/demo/checkup-gate-showcase
cd /tmp/pdd-gate-demo/examples/checkup_gate_demo
pip install -e "../..[dev]"
export PDD_SKIP_UPDATE_CHECK=1 PDD_AUTO_UPDATE=false CI=1

./run_offline_checks.sh
CLEAN=1 ./run_demo.sh
```
