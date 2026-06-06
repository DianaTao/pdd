# Prompt Repair Demo — `pdd checkup --prompt-repair`

This demo shows the non-interactive prompt repair feature (Issue #1422) in action
on a realistic subscription billing service prompt.

## What the Feature Does

`pdd checkup <prompt-file> --prompt-repair best-effort` implements a deterministic
**check → repair → re-check** cycle:

1. **Check**: runs the full `pdd.prompt_source_set_report.v1` structured checkup
   (lint + contract + coverage + gate) on the prompt.
2. **Repair**: if the report shows failures, an LLM proposes bounded JSON patches
   (vocabulary additions, rule clarifications) using the structured report as the
   oracle — not just lint.
3. **Re-check**: runs the structured checkup again after applying patches to verify
   improvement.

## The Demo Prompt

`subscription_billing_before_python.prompt` is a realistic billing-service contract
with five undefined vague terms and four rules lacking observable outcomes —
a common first-draft problem in PDD prompt authoring.

### Before repair — 9 lint issues

```
pdd checkup lint demos/prompt_repair/subscription_billing_before_python.prompt
```

```
[warn] "active"      — Vague term used in contract_rules without a <vocabulary> definition.
[warn] "valid"       — Vague term used in contract_rules without a <vocabulary> definition.
[warn] "gracefully"  — Vague term used in contract_rules without a <vocabulary> definition.
[warn] "reasonable"  — Vague term used in contract_rules without a <vocabulary> definition.
[warn] "successful"  — Vague term used in contract_rules without a <vocabulary> definition.
[warn] (R1) — Rule contains a vague term but no observable outcome verb.
[warn] (R2) — Rule contains a vague term but no observable outcome verb.
[warn] (R3) — Rule contains a vague term but no observable outcome verb.
[warn] (R4) — Rule contains a vague term but no observable outcome verb.

9 issues
```

### After repair — 0 lint issues

`subscription_billing_after_python.prompt` shows the target state: precise
vocabulary definitions eliminate the VAGUE_TERM issues, and concrete observable
outcome verbs (`write`, `return HTTP 200`, `emit`) eliminate the
no-observable-outcome issues.

```
pdd checkup lint demos/prompt_repair/subscription_billing_after_python.prompt
```

```
0 issues — ✓ clean
```

## Running the Demo

> Requires a configured LLM provider (`PDD_MODEL_DEFAULT` or equivalent).
> Use `--dry-run` (coming) or the test suite below for a provider-free demo.

```bash
# Step 1 — see the issues
pdd checkup lint demos/prompt_repair/subscription_billing_before_python.prompt

# Step 2 — run repair in best-effort mode (LLM applies one pass of patches)
cp demos/prompt_repair/subscription_billing_before_python.prompt /tmp/billing_demo.prompt
pdd checkup /tmp/billing_demo.prompt --prompt-repair best-effort

# Step 3 — compare
pdd checkup lint /tmp/billing_demo.prompt
```

For multi-pass repair (more thorough):

```bash
pdd checkup /tmp/billing_demo.prompt \
  --prompt-repair best-effort \
  --max-prompt-repair-rounds 2
```

For strict mode (fails unless 0 issues remain after repair):

```bash
pdd checkup /tmp/billing_demo.prompt --prompt-repair strict
```

## Running the Tests (No LLM Required)

All six demo tests mock the LLM and run deterministically:

```bash
pytest -vv tests/test_prompt_repair_demo.py
```

| Test | What it proves |
|------|----------------|
| `test_before_prompt_has_known_issues` | Scanner catches all 5 vague terms + 4 observable-outcome issues in the before prompt |
| `test_after_prompt_is_clean` | Manually-crafted after prompt passes lint with 0 issues — target state is achievable |
| `test_repair_loop_applies_vocabulary_patches` | One LLM pass (ADD_VOCABULARY ×5) reduces issue count and writes `<vocabulary>` block |
| `test_repair_loop_two_pass_convergence` | Two-pass repair (vocabulary then clarify) converges to 0 issues — strict mode passes |
| `test_cli_prompt_target_routes_without_github_guard` | `pdd checkup <prompt-file>` exits 0, no longer rejected with "TARGET must be a GitHub issue URL" |
| `test_check_repair_recheck_cycle_end_to_end` | Full check → repair → recheck cycle: `run_checkup_prompt` called twice, repair LLM invoked once |

## What Changed vs. the Old Behaviour

| Aspect | Before #1422/#1426 | After |
|--------|-------------------|-------|
| `pdd checkup <prompt-file>` | Exits 2: "TARGET must be a GitHub issue URL" | Routes to `run_checkup_prompt` via `is_prompt_shaped_target` |
| `--prompt-repair` oracle | Lint-only (`scan_prompt`) | Full `pdd.prompt_source_set_report.v1` (lint + coverage + contract + gate) |
| Repair position (agentic path) | Before orchestrator (blind to checkup outcome) | After structured pre-flight check, re-verified after repair |
| Template crash | `str.format()` raises `KeyError` on `{` in `prompt_repair_LLM.prompt` | Braces escaped; template formats correctly |
| Prompt discovery | `git diff HEAD` (misses clean worktrees) | `git diff origin/main...HEAD` (PR-aware) |
| Write safety | Direct `path.write_text()` — crash leaves corrupt file | Atomic sibling-rename + rollback if no improvement |
