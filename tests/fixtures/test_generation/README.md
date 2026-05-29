# Contract-rule test generation fixtures

Used by issue #821 / PR #1283 regression and CLI smoke tests.

- `refund_policy_python.prompt` — module prompt with one `MUST` and one `MUST NOT` rule (`R1`, `R2`).
- `refund_policy.py` — minimal implementation under test.

Offline regression (no LLM):

```bash
PYTHONPATH=. pytest -q tests/test_generate_test_llm_preprocess.py
PYTHONPATH=. pytest -q tests/test_cmd_test_main.py -k "context_test_prompt or contract_rule_planning"
```

Cloud E2E (real PDD Cloud `generateTest`, costs credits; requires `pdd auth login`):

```bash
PDD_RUN_REAL_LLM_TESTS=1 PYTHONPATH=. pytest -q tests/commands/test_contract_rule_test_smoke.py -v
PDD_RUN_REAL_LLM_TESTS=1 PYTHONPATH=. pytest -q tests/test_cmd_test_main.py -k cloud_e2e_contract_rules_merge -v
```

Manual CLI walkthrough: branch `docs/issue-821-manual-test-plan` → `examples/contract_rule_test_demo/README.md`.
