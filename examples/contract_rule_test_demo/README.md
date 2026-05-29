# Contract-rule test generation — manual test plan (Issue #821 / PR #1283)

Step-by-step terminal commands for branch **`DianaTao:feat/issue-821-contract-rule-tests`**.

| Link | URL |
|------|-----|
| Issue | https://github.com/promptdriven/pdd/issues/821 |
| PR | https://github.com/promptdriven/pdd/pull/1283 |

Run everything below from the **repository root** unless a step says to `cd` elsewhere.

---

## What you are validating

| # | What we test | Why it matters for #821 |
|---|----------------|-------------------------|
| 1 | Shared `context/test.prompt` content | Contract-rule planning rules live here and must stay alongside mocking/isolation/merge guidance |
| 2 | LLM template preprocess | Legacy `pdd test` must **inline** that context into the prompt the model sees (broken include expansion blocked delivery) |
| 3 | Automated pytest | CI regressions for preprocess, CLI wiring, and `--merge` |
| 4 | Workspace setup | Live demo needs `context/test.prompt` + a module with `<contract_rules>` + an accumulated test file |
| 5 | **`pdd test --manual --merge`** | End-to-end: contract rules in module prompt → generated tests; existing tests preserved |
| 6 | Merged test file review | Human check: R1/R2 coverage, rule IDs, observable assertions |
| 7 | (Optional) Example-based **`pdd test`** | Second legacy path also expands `context/test.prompt` |

---

## Prerequisites

```bash
git fetch https://github.com/DianaTao/pdd.git feat/issue-821-contract-rule-tests
git checkout feat/issue-821-contract-rule-tests

pip install -e ".[dev]"
pdd setup
export PDD_PATH="$PWD/pdd"
export REPO_ROOT="$PWD"
```

| Steps | API key? |
|-------|----------|
| 1–4, 3 (pytest) | No |
| 5–7 | Yes (or credentials from `pdd setup`) |

---

## Test 1 — Shared context file (static)

**Testing for:** `context/test.prompt` tells test generation to plan from `contract_rules` (MUST, MUST NOT, rule IDs, TODO/skip, merge) without removing existing external-boundary or isolation rules.

```bash
grep -n "CONTRACT RULE TEST PLANNING" context/test.prompt
grep -n "behavioral test for each MUST rule" context/test.prompt
grep -n "negative test for each MUST NOT rule" context/test.prompt
grep -n "Preserve existing accumulated tests" context/test.prompt
grep -n "Tests must mock ALL external service boundaries" context/test.prompt
```

**Pass:** All five patterns match at least one line.

---

## Test 2 — Preprocess inlines `context/test.prompt` (no `pdd` CLI)

**Testing for:** After preprocessing, `generate_test_LLM` and `generate_test_from_example_LLM` contain contract guidance and **no** leftover `<include … context/test.prompt …>` tag. This is the legacy path `pdd test` uses internally before calling the LLM.

### 2a — Code-based template (`generate_test_LLM`)

```bash
export PDD_QUIET=1

python - <<'PY'
from pdd.load_prompt_template import load_prompt_template
from pdd.preprocess import preprocess

text = preprocess(
    load_prompt_template("generate_test_LLM"),
    recursive=False,
    double_curly_brackets=False,
)
checks = {
    "CONTRACT RULE TEST PLANNING": "CONTRACT RULE TEST PLANNING" in text,
    "MUST NOT guidance": "negative test for each MUST NOT rule" in text,
    "merge guidance": "Preserve existing accumulated tests" in text,
    "include expanded": "<include optional>context/test.prompt</include>" not in text,
}
for label, ok in checks.items():
    print(f"{label}: {ok}")
if not all(checks.values()):
    raise SystemExit(1)
print("PASS generate_test_LLM preprocess")
PY
```

### 2b — Example-based template (`generate_test_from_example_LLM`)

```bash
python - <<'PY'
from pdd.load_prompt_template import load_prompt_template
from pdd.preprocess import preprocess

text = preprocess(
    load_prompt_template("generate_test_from_example_LLM"),
    recursive=False,
    double_curly_brackets=False,
)
checks = {
    "CONTRACT RULE TEST PLANNING": "CONTRACT RULE TEST PLANNING" in text,
    "include expanded": "<include optional>./context/test.prompt</include>" not in text,
}
for label, ok in checks.items():
    print(f"{label}: {ok}")
if not all(checks.values()):
    raise SystemExit(1)
print("PASS generate_test_from_example_LLM preprocess")
PY
```

**Pass:** Every check prints `True`; script exits 0.

---

## Test 3 — Automated regression (pytest)

**Testing for:** Unit tests guard prompt source text, preprocess output, `cmd_test_main` forwarding of `<contract_rules>`, and CLI `--merge` behavior (mocked LLM).

```bash
PYTHONPATH=. pytest -q tests/test_generate_test_llm_preprocess.py
PYTHONPATH=. pytest -q tests/commands/test_contract_rule_test_smoke.py
PYTHONPATH=. pytest -q tests/test_cmd_test_main.py -k "contract or context_test_prompt"
```

**Pass:** All tests pass (expect 2 + 1 + several for the last command).

---

## Test 4 — Prepare live-demo workspace

**Testing for:** Nothing yet — this builds an isolated mini-project so `pdd test` picks up `context/test.prompt` from the current repo and uses the bundled **R1 MUST / R2 MUST NOT** fixture.

```bash
export DEMO_ROOT="$REPO_ROOT/examples/contract_rule_test_demo"
rm -rf "$DEMO_ROOT/workspace"
mkdir -p "$DEMO_ROOT/workspace/context" "$DEMO_ROOT/workspace/tests" "$DEMO_ROOT/workspace/src"

cp "$REPO_ROOT/context/test.prompt" "$DEMO_ROOT/workspace/context/test.prompt"
cp "$DEMO_ROOT/prompts/refund_policy_python.prompt" "$DEMO_ROOT/workspace/refund_policy_python.prompt"
cp "$DEMO_ROOT/src/refund_policy.py" "$DEMO_ROOT/workspace/src/refund_policy.py"
cp "$DEMO_ROOT/src/refund_policy_example.py" "$DEMO_ROOT/workspace/src/refund_policy_example.py"

cat > "$DEMO_ROOT/workspace/tests/test_refund_policy.py" <<'EOF'
"""Accumulated test — must survive pdd test --merge."""


def test_existing_accumulated_refund_case():
    assert True
EOF

ls -la "$DEMO_ROOT/workspace"
```

**Pass:** `workspace/` contains `context/test.prompt`, `refund_policy_python.prompt`, `src/refund_policy.py`, and `tests/test_refund_policy.py`.

---

## Test 5 — `pdd test --manual --merge` (primary #821 demo)

**Testing for:**

- Module prompt `<contract_rules>` (R1, R2) reaches the test generator.
- LLM applies contract-aware guidance from `context/test.prompt`.
- New tests reference rule IDs when practical.
- **`--merge`** appends to the existing file without removing `test_existing_accumulated_refund_case`.

```bash
export PDD_FORCE_LOCAL=1
# export OPENAI_API_KEY=sk-...   # if not using ~/.pdd from pdd setup

cd "$DEMO_ROOT/workspace"

pdd --local test --manual \
  refund_policy_python.prompt \
  src/refund_policy.py \
  --existing-tests tests/test_refund_policy.py \
  --merge \
  --output tests/test_refund_policy_generated.py
```

**Pass:** Command exits 0; `tests/test_refund_policy.py` grows with new test functions.

---

## Test 6 — Verify merged output

**Testing for:** Generated artifact quality (not re-running `pdd`).

```bash
cd "$DEMO_ROOT/workspace"

grep -n "test_existing_accumulated_refund_case" tests/test_refund_policy.py
grep -nE 'R1|R2|test_R[12]' tests/test_refund_policy.py

export PYTHONPATH="$DEMO_ROOT/workspace/src:$PYTHONPATH"
pytest -q tests/test_refund_policy.py -v
```

| Check | What it proves |
|-------|----------------|
| Accumulated test still present | `--merge` preserved permanent tests |
| `R1` / `R2` in names or comments | Rule-ID traceability from `<contract_rules>` |
| `pytest` passes | Generated imports and assertions are runnable |

**Pass:** Stub test remains; R1 and R2 are visible; pytest succeeds (or only minor import fixes needed).

---

## Test 7 (optional) — Example-based `pdd test`

**Testing for:** The example-based legacy path (`generate_test_from_example_LLM`) also receives contract guidance when the module prompt has `<contract_rules>`.

```bash
cd "$DEMO_ROOT/workspace"

pdd --local test --manual \
  refund_policy_python.prompt \
  src/refund_policy_example.py \
  --output tests/test_refund_policy_from_example.py
```

**Pass:** New file `tests/test_refund_policy_from_example.py` references R1/R2 in test names or comments.

---

## Fixture reference

**`prompts/refund_policy_python.prompt`**

| Rule | Modal | Expected test style |
|------|-------|---------------------|
| R1 | MUST | Positive: in-range refund → `"approved"` |
| R2 | MUST NOT | Negative: refund > charge → `"rejected"` |

**`src/refund_policy.py`** — implementation under test.

---

## Sign-off checklist

- [ ] Test 1 — `context/test.prompt` has contract + legacy guidance  
- [ ] Test 2 — Both LLM templates preprocess with contract text inlined  
- [ ] Test 3 — Pytest regression green  
- [ ] Test 5 — `pdd test --manual --merge` succeeds  
- [ ] Test 6 — Merged file keeps stub + R1/R2-visible tests  

**Tester / date:** _______________  
**Result:** Pass / Fail — notes: _______________

---

## Related docs

- [`docs/manual_test_plan_issue_821.md`](../../docs/manual_test_plan_issue_821.md) — extended checklist  
- [`tests/fixtures/test_generation/README.md`](../../tests/fixtures/test_generation/README.md) — CI fixture copy  

## Out of scope

- `pdd contracts check` / coverage enforcement on generated tests  
- Agentic non-Python paths (inline rules in `agentic_test_generate_LLM.prompt` only)  
- Full-repo `make lint` 10/10  
