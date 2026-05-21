# prompt_lint_contract_workflow — decomposed command playbook

A worked example that shows how to drive the deterministic prompt lint +
contracts pipeline **command-by-command** against the same `foo_work` handler
used in [`prompt_lint_contract_e2e_demo/`](../prompt_lint_contract_e2e_demo/).

Unlike the sibling demo (which wraps everything in `demo.sh`), this directory
keeps the **artifacts of each phase** so you can inspect them in isolation:

```
prompt_lint_contract_workflow/
├── prompts/
│   └── foo_work_work.prompt        # work copy with <contract_rules>, <vocabulary>, <formalization>
└── reports/
    ├── phase1_lint.json            # pdd prompt lint --json
    ├── phase1_check.json           # pdd contracts check --json
    ├── phase1_compile.json         # pdd contracts compile --json
    ├── phase1_formalization.json   # pdd contracts compile --formalization
    ├── phase1_coverage.json        # pdd coverage --contracts --json
    └── clarify.json                # pdd prompt clarify --ambiguity --json
```

## Replaying phase 1 manually

The prompt is structured so the deterministic commands run in this order:

```bash
cd examples/prompt_lint_contract_workflow

# 1. Surface vague terms before they reach contracts
pdd prompt lint --json prompts/foo_work_work.prompt > reports/phase1_lint.json

# 2. Sanity-check rule IDs, modals, and waiver hygiene
pdd contracts check --json prompts/foo_work_work.prompt > reports/phase1_check.json

# 3. Compile the contract rules to IR
pdd contracts compile --json prompts/foo_work_work.prompt > reports/phase1_compile.json

# 4. Confirm rules have story/test/waiver evidence (none yet -> all unchecked)
pdd coverage --contracts --json prompts/foo_work_work.prompt > reports/phase1_coverage.json
```

The captured `reports/*.json` files are the **reference output** for those four
commands at the current prompt revision; diff against them to catch regressions
when iterating on the prompt.

## Status

This directory is a **decomposed command playbook**, not a one-button demo.
A `run_phase1.sh` wrapper and a `guidance/` subfolder of authoring notes are
planned follow-on work; until then, the canonical end-to-end runner is
[`prompt_lint_contract_e2e_demo/demo.sh`](../prompt_lint_contract_e2e_demo/demo.sh).

## See also

- [`docs/prompt_lint.md`](../../docs/prompt_lint.md)
- [`docs/contract_check.md`](../../docs/contract_check.md)
- [`docs/coverage_contracts.md`](../../docs/coverage_contracts.md)
