# Prompt gate — end-to-end validation (#1420 / PR #1428)

This note documents a runnable, deterministic end-to-end validation of the
prompt-aware `pdd checkup` source-set report and the automatic prompt gate that
`pdd generate` and `pdd change` invoke when they touch `.prompt` files.

It exercises the real CLIs in real subprocesses against disposable fixture
projects. **The only thing stubbed is the model/provider boundary** — the prompt
gate, `change_main`, gate-mode resolution from `.pddrc`, and the
`pdd.prompt_source_set_report.v1` report all run for real, so the asserted exit
codes are genuine process results from the gate.

## What runs for real vs. stubbed

| Component | Real? |
| --- | --- |
| `pdd checkup` / `pdd change` / `pdd generate` command bodies | ✅ real |
| `change_main` (orchestration + prompt save) | ✅ real |
| `maybe_run_workflow_prompt_gate` + the gate it drives | ✅ real |
| Gate-mode resolution from `.pddrc` / `pyproject.toml` | ✅ real |
| `pdd.prompt_source_set_report.v1` source-set report | ✅ real |
| `change_func` (the LLM call in `pdd change`) | 🔁 stubbed |
| `construct_paths` / `resolve_effective_config` (path/config plumbing) | 🔁 stubbed |
| `run_agentic_architecture` (model-backed prompt writer in `pdd generate`) | 🔁 stubbed |

The stub harness is `tests/e2e/_fake_provider_cli.py`; it installs the provider
stubs and then runs the real CLI so a genuine OS exit code is produced.

## How to run

```bash
# Focused pytest (deterministic, no network/model, ~25s):
pytest -vv tests/e2e/test_prompt_gate_workflow.py

# Human-readable transcript (command, changed .prompt, gate output, exit code):
python scripts/prompt_gate_e2e_demo.py

# Pure-real checkup smoke (no stubs at all):
PDD_AUTO_UPDATE=false python -m pdd.cli checkup tests/fixtures/prompt_lint/clean.prompt --json
```

## Scenarios and expected results

| Scenario | Command (abridged) | Gate mode source | Exit | Evidence |
| --- | --- | --- | --- | --- |
| checkup | `pdd checkup clean.prompt --json` | n/a | 0/1 | schema `pdd.prompt_source_set_report.v1`, `lint`/`contract`/`coverage` checks |
| checkup-nested | `pdd checkup --project-root <proj> <proj>/prompts/...` from an **external cwd** | n/a | 0/1 | `0` coverage rules `unchecked` ⇒ story under the project root was found ⇒ rooting fix works |
| change-warn | `pdd change --manual ... --output prompts/feature_python.prompt` | `.pddrc prompt_gate: warn` | 0 | `saved to` then `Prompt checkup: needs attention`, run continues |
| change-strict | same `+ --prompt-checkup strict` | CLI flag | 2 | `saved to` then `Prompt checkup blocked downstream change steps (exit 2)` |
| change-off | same | `.pddrc prompt_gate: off` (unquoted ⇒ YAML `False`) | 0 | prompt saved, **no** gate output ⇒ gate disabled by config |
| generate-warn | `pdd generate <issue> --prompt-checkup warn` | CLI flag | 0 | orchestrator writes `.prompt`, gate reports, continues |
| generate-strict | `pdd generate <issue>` | `.pddrc prompt_gate: strict` | 2 | orchestrator writes `.prompt`, gate blocks |

The `change-strict` / `generate-strict` transcripts show the prompt write line
(`saved to ...` / the orchestrator's write) **before** the gate's block message,
confirming the gate runs *after* the prompt write and changes the process result.

## How this maps to the PR #1428 review concerns

* **Config-based disabling works** — `change-off` writes an unquoted
  `prompt_gate: off` to `.pddrc` (which PyYAML loads as boolean `False`) and the
  gate is skipped, exit 0.
* **Coverage/gate lookup is anchored to the project root** — `checkup-nested`
  runs from an external cwd with `--project-root` and reports `0` `unchecked`
  contract-coverage rules, proving the story under `<project_root>/user_stories`
  is found, in the same kind of invocation users actually run (not just a unit
  call).
* **Both gate outcomes are exercised through the real workflow** — `*-warn`
  continues while reporting findings; `*-strict` exits non-zero.
