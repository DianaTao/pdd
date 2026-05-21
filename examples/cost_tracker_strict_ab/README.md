# cost_tracker_strict_ab — WIP scaffolding

This directory hosts authoring artifacts for a planned strict A/B demo built on
top of [`contract_commands_cost_tracker_e2e_demo/`](../contract_commands_cost_tracker_e2e_demo/).

It is **not a runnable demo on this branch.** The deterministic runner, golden
pytest harness, and `demo.sh` wrapper are tracked as follow-on work alongside
`pdd evidence`, `pdd gate`, and `pdd contracts drift`. The relevant CI tests
(`tests/test_cost_tracker_strict_ab.py`) skip themselves when those scripts are
absent.

## What is here

```
cost_tracker_strict_ab/
├── prompts/
│   └── cost_tracker_work_python.prompt         # working copy of the spec
├── src/
│   └── edit_file_tool/cost_tracker_utility*.py # captured before/after sources
├── tests/
│   ├── test_cost_tracker_work_before.py        # captured before snapshot
│   └── test_cost_tracker_work_after.py         # captured after snapshot
└── reports/                                    # captured A/B output for replay
    ├── evidence_*.json
    ├── experiment_a*.json
    ├── ab_live.json
    ├── artifacts/  (prompt + src + tests snapshots)
    └── diffs/      (prompt/src/tests unified diffs)
```

## What is *not* here yet

- `scripts/run_experiment_a.py` — deterministic Experiment A driver
  (gate / evidence / drift). Depends on `pdd evidence` + `pdd contracts drift`.
- `scripts/run_golden_pytest.py` — golden test harness that stages the package
  layout under `edit_file_tool/` before running the captured pytest snapshot.
- `demo.sh` — `--live-ab` and `--cleanup` orchestrator referenced by
  `tests/test_cost_tracker_strict_ab.py::test_experiment_b_live_ab_pipeline`.

Until those land, the captured artifacts under `reports/` are the canonical
reference output. Treat this directory as the regression fixture for the
forthcoming `pdd evidence`/`pdd contracts drift` rollout.

For a runnable contracts pipeline today, use the sibling
[`contract_commands_cost_tracker_e2e_demo/`](../contract_commands_cost_tracker_e2e_demo/)
which exercises `pdd prompt lint`, `pdd contracts check/compile`, and
`pdd coverage --contracts` against the same source prompt.
