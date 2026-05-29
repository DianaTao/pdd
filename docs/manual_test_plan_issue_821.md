# Manual test plan — Issue #821 / PR #1283

**Branch:** `DianaTao:feat/issue-821-contract-rule-tests`  
**Upstream PR:** https://github.com/promptdriven/pdd/pull/1283  
**Issue:** https://github.com/promptdriven/pdd/issues/821  

**Goal:** Verify that `pdd test` (legacy Python path) receives contract-rule test-planning guidance when a module prompt contains `<contract_rules>`, including MUST behavioral tests, MUST NOT negative tests, rule-ID traceability, and `--merge` preservation.

**Primary manual test plan (individual commands, with “what we test” per step):**  
[`examples/contract_rule_test_demo/README.md`](../examples/contract_rule_test_demo/README.md)

---

## Quick pointer

| Test | Command type | What it validates |
|------|----------------|-------------------|
| 1 | `grep` | `context/test.prompt` contract + legacy guidance |
| 2 | `python` + preprocess | LLM templates inline contract context |
| 3 | `pytest` | Automated regressions |
| 4 | `cp` / `mkdir` | Demo workspace for live `pdd test` |
| 5 | **`pdd test --manual --merge`** | End-to-end contract-rule test generation |
| 6 | `grep` / `pytest` | Merged output quality |
| 7 | **`pdd test --manual`** (optional) | Example-based path |

Setup:

```bash
git checkout feat/issue-821-contract-rule-tests
pip install -e ".[dev]"
pdd setup
export PDD_PATH="$PWD/pdd"
export REPO_ROOT="$PWD"
```

Then follow Tests 1–7 in [`examples/contract_rule_test_demo/README.md`](../examples/contract_rule_test_demo/README.md).

---

## Out of scope

- `pdd contracts check` / coverage enforcement on generated tests  
- Full-repo `make lint` 10/10  
- DianaTao/pdd#40 checkup hygiene (separate PR)  
