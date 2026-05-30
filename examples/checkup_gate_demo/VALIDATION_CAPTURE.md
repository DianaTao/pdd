# Live validation capture — checkup gate demo

Auditable output for PR [#1260](https://github.com/promptdriven/pdd/pull/1260) /
evidence [#1256](https://github.com/promptdriven/pdd/pull/1256).

**Branch:** `demo/checkup-gate-showcase`  
**Captured:** 2026-05-30 (isolated worktree, no changes to other feature branches)  
**Environment:** macOS, Python 3.13, `pdd` 0.0.255.dev0 (editable install), `CI=1`, `PDD_SKIP_UPDATE_CHECK=1`

## Commands and exit codes

| Step | Command | Exit code | Notes |
|------|---------|-----------|-------|
| Offline | `./run_offline_checks.sh` | **0** | 24 pytest passed; offline gate scenarios OK |
| Live (partial script) | `CLEAN=1 ./run_demo.sh` | **1** | Stopped after step 3 because `set -e` + failed sync (see fix in `run_demo.sh`) |
| Live sync | `pdd sync refund --evidence` | **1** | Failed: coverage 0.0% below target 90.0% |
| Live contract | `pdd checkup contract check prompts/` | **0** | 0 errors |
| Live coverage | `pdd checkup coverage prompts/` | **0** | 2/3 rules checked |
| Live gate | `pdd checkup gate refund --json` | **1** | `passed: false` (see JSON below) |

## Live sync summary (step 1)

```
Overall status: Failed
Details: Sync failed: Coverage 0.0% below target 90.0% after 2 test_extend attempts
Total time: 197.18s | Total cost: $0.6464
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

**`failures[].code`:** `stories_pass`, `verify_not_available`, `unit_tests_pass`

## Interpretation (gate working as designed)

- Sync failed on test coverage → manifest honestly records `unit_tests: failed`.
- Verify step did not complete in sync → `verify: not_available`.
- Story detection is not part of sync → `detect_stories: not_applicable`.
- Default policy is fail-closed → gate returns `passed: false` with stable failure codes.

This matches the offline failed-sync demo (`python demo_failed_sync_gate.py`) and unit tests in `tests/test_checkup_gate_demo.py`.

## Reproduce

```bash
git fetch fork demo/checkup-gate-showcase
git worktree add /tmp/pdd-gate-demo fork/demo/checkup-gate-showcase
cd /tmp/pdd-gate-demo/examples/checkup_gate_demo
pip install -e "../..[dev]"
export PDD_SKIP_UPDATE_CHECK=1 PDD_AUTO_UPDATE=false CI=1

./run_offline_checks.sh
CLEAN=1 ./run_demo.sh    # continues through gate after sync fix
# or manually after sync:
pdd checkup gate refund --json
```

## Debug notes: can gate pass after failed sync?

| Scenario | Gate `passed` under default policy? | Status |
|----------|-------------------------------------|--------|
| Normal failed sync writes fresh manifest (`unit_tests: failed`, etc.) | **false** | Working as designed (this capture) |
| Stale `refund.latest.json` from an older successful run, new sync throws before `--evidence` write | **true** (bug) | Fixed: sync `--evidence` now refreshes manifest on exception |
| Inconsistent `overall_success: true` with `success: false` in language results | could mark tests **passed** (bug) | Fixed: `validation_from_sync` prefers per-language outcomes |

Regression tests: `tests/test_gate_failed_sync.py`.
