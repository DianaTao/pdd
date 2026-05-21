# Token Bucket — generate + test Z3 demo

This demo shows how contract-enriched prompts guide `pdd generate` and `pdd test`
to produce rule-linked, formalization-aware tests — including Z3-style invariant
proofs when the LLM supports it.

The domain is a **token bucket rate limiter**: pure integer state, no filesystem,
no network, no time. This makes it ideal for `FORMAL_CANDIDATE` classification and
Z3 proof generation.

---

## What this demo tests

The demo is split into four experiments, each testing a different layer of the
prompt-as-source-of-truth pipeline:

| Experiment | Type | What it tests | CI suitable? |
|---|---|---|---|
| A. Prompt quality | deterministic | lint/check/compile recognize enriched prompt | ✓ merge CI |
| B. Test generation | LLM | enriched prompt → rule-linked + Z3 tests | opt-in / mocked |
| C. Full E2E | LLM | plain vs enriched end-to-end generate + test + pytest | nightly / manual |
| D. Coverage evidence | deterministic (after B/C) | R1–R4 connected to stories/tests | ✓ after generation |

---

## Quick start

```bash
# Install from repo root
pip install -e /path/to/pdd
```

**Experiment A** is fully deterministic — no cloud needed:
```bash
bash demo.sh --exp-a
```

**Experiments B and C** call `pdd generate` and `pdd test`, which use PDD Cloud.
Authenticate first using one of these options:

```bash
# Option 1 — interactive login (stored in system keyring)
pdd auth login

# Option 2 — inject token directly (best for CI / scripted runs)
export PDD_JWT_TOKEN="$(pdd auth token)"

# Option 3 — custom cloud endpoint
export PDD_CLOUD_URL="https://your-cloud-url"
export PDD_JWT_TOKEN="<your-token>"
```

Then run:
```bash
# All four experiments
bash demo.sh

# Or just the LLM experiments
bash demo.sh --exp-b
bash demo.sh --exp-c
```

**Optional:** install `z3-solver` to execute Z3 formal proof tests rather than skip them:
```bash
pip install z3-solver
bash demo.sh --exp-d
```

---

## The two prompts

### `prompts/token_bucket_plain_python.prompt` — plain, no contracts

Describes the same token bucket domain in plain prose. No `<contract_rules>`,
no `<vocabulary>`, no `<formalization>`. This is the **before** arm.

Expected behavior:
- `pdd prompt lint` reports vague terms (`appropriate`, `allowed`, `valid`)
- `pdd contracts check` — not applicable (no rules)
- `pdd contracts compile` — not applicable
- `pdd test` generates behavioral tests, likely no R# markers or Z3 proofs

### `prompts/token_bucket_python.prompt` — contract + formalization enriched

Same domain with four structured sections added. This is the **after** arm.

**`<contract_rules>`** — strict When/MUST rules:
```
R1: MUST reject consume if tokens_available < requested_tokens
R2: MUST reduce tokens_available by exactly requested_tokens on success
R3: MUST NOT set tokens_available above capacity on refill
R4: MUST raise ValueError if capacity is not a positive integer
```

**`<vocabulary>`** — removes lint ambiguity for all key terms

**`<acceptance_tests>`** — concrete Given/When/Then scenarios for R1–R4

**`<formalization>`** — rule-linked Z3 targets with explicit variables,
assumptions, and properties that the test generator can convert directly
into Z3 `Solver` assertions

Expected behavior:
- `pdd prompt lint` — zero errors, fewer or equal warnings
- `pdd contracts check` — R1–R4 all pass structural check
- `pdd contracts compile` — 4 rules compiled, 0 errors
- `pdd test` — generates tests with R1–R4 markers; Z3-style proofs best-effort

---

## Experiment A — Prompt quality (deterministic)

```bash
bash demo.sh --exp-a
```

Runs `pdd prompt lint`, `pdd contracts check`, and `pdd contracts compile` on
both prompts and compares.

Expected contrast:

| Check | Plain prompt | Enriched prompt |
|---|---|---|
| `pdd prompt lint` | lint warnings | zero errors |
| `pdd contracts check` | not applicable | passes R1–R4 |
| `pdd contracts compile` | not applicable | 4 rules, 0 errors |

Reports written to: `reports/lint_plain.json`, `reports/lint_contract.json`,
`reports/check_contract.json`, `reports/compile_contract.json`

---

## Experiment B — Test generation on the same implementation (LLM)

```bash
bash demo.sh --exp-b
```

Generates one implementation from the enriched prompt, then generates tests
twice — once from each prompt. This isolates the effect of the **test prompt**
from codegen variance.

```bash
# One implementation
pdd generate prompts/token_bucket_python.prompt --output src/token_bucket.py

# Two test files from different prompts
pdd test --manual prompts/token_bucket_plain_python.prompt src/token_bucket.py \
    --output tests/test_plain.py

pdd test --manual prompts/token_bucket_python.prompt src/token_bucket.py \
    --output tests/test_contract.py
```

Hard assertions:
- `test_contract.py` contains R1, R2, R3, R4 markers
- `test_contract.py` compiles and pytest runs

Soft / best-effort:
- `test_contract.py` contains Z3-style tests or `pytest.importorskip("z3")`

> **Note on Z3 generation:** The structured `<formalization>` block increases
> the probability that `pdd test` emits Z3 proof tests, but this depends on
> LLM behavior and is not guaranteed on every run.

Report: `reports/experiment_b.json` — rule marker counts and Z3 detection

---

## Experiment C — Full E2E before/after (LLM)

```bash
bash demo.sh --exp-c
```

Generates separate implementations and tests from each prompt, then compiles and
runs both with pytest. This tests the complete workflow end-to-end.

```bash
# Before arm
pdd generate prompts/token_bucket_plain_python.prompt --output src/token_bucket_before.py
pdd test --manual prompts/token_bucket_plain_python.prompt src/token_bucket_before.py \
    --output tests/test_before.py

# After arm
pdd generate prompts/token_bucket_python.prompt --output src/token_bucket_after.py
pdd test --manual prompts/token_bucket_python.prompt src/token_bucket_after.py \
    --output tests/test_after.py
```

Hard assertions: both implementations and test files compile and pytest passes.

> This experiment has more variance than Experiment B because both codegen and
> test generation can differ. The correct claim is: "the enriched prompt produced
> a working implementation and tests in this run", not "enriched always beats plain".

Reports: `reports/pytest_before.txt`, `reports/pytest_after.txt`

---

## Experiment D — Contract coverage evidence (deterministic)

```bash
bash demo.sh --exp-d
```

Requires Experiment B or C to have run first (needs `tests/` to exist).

```bash
pdd coverage --contracts prompts/token_bucket_python.prompt \
    --stories-dir user_stories/ --tests-dir tests/ --json > reports/coverage.json
```

Expected: R1–R4 classified as `checked` or `story-only`.

> This requires R# markers in generated test names or comments. If tests lack
> markers, rules appear `unchecked`. The user story covers all four rules as a
> fallback, so R1–R4 will be at minimum `story-only`.

Also writes `reports/z3_status.json`:
```json
{
  "z3_test_generated": true,
  "z3_installed": false,
  "z3_test_executed": false,
  "z3_test_skipped": true
}
```

---

## Pass/fail criteria

### Hard (demo must pass these)

- [ ] Enriched prompt: zero lint errors
- [ ] Enriched prompt: R1–R4 pass `contracts check` and `contracts compile` with 0 errors
- [ ] Plain prompt: reported as not_applicable for contracts, not as failure
- [ ] `tests/test_contract.py`: contains R1–R4 markers, compiles, pytest runs
- [ ] Before and after generated files: both compile
- [ ] R1–R4 in coverage: at least `story-only` (user story provides baseline)

### Soft (best-effort, LLM-dependent)

- [ ] `tests/test_contract.py` contains Z3-style test or `pytest.importorskip("z3")`
- [ ] Enriched prompt has zero lint warnings
- [ ] After arm has more R# markers than before arm
- [ ] Z3 formal proofs execute when `z3-solver` is installed

---

## File layout

```
examples/generate_test_z3_demo/
├── README.md
├── demo.sh                                  ← all 4 experiments
├── prompts/
│   ├── token_bucket_plain_python.prompt     ← plain, no contracts (before arm)
│   └── token_bucket_python.prompt           ← contract + formalization (after arm)
├── user_stories/
│   └── story__token_bucket.md               ← covers R1–R4 for coverage fallback
├── src/                                     ← gitignored, generated by pdd generate
├── tests/                                   ← gitignored, generated by pdd test
└── reports/                                 ← gitignored, generated by demo.sh
```

---

## Troubleshooting

**`pdd` not found or wrong version**
```bash
pip install -e /path/to/pdd
which pdd          # must point to editable install
pdd --version      # should show 0.0.218.dev* not 0.0.243
```

**Cloud auth not confirmed (experiments B, C fail)**
```bash
# Check current status
pdd auth status

# Login interactively (device flow)
pdd auth login

# Or export a token for CI/scripted use
export PDD_JWT_TOKEN="$(pdd auth token)"

# For a custom cloud endpoint
export PDD_CLOUD_URL="https://your-cloud-url"
export PDD_JWT_TOKEN="<your-token>"
```

**Keyring times out (`auth status` hangs)**
```bash
# Bypass keyring entirely by injecting the token
export PDD_JWT_TOKEN="<paste-token-here>"
bash demo.sh --exp-b
```

**Z3 proofs skipped**

This is expected when `z3-solver` is not installed. Install it to un-skip:
```bash
pip install z3-solver
```

**`pdd test` writes `test_contract_1.py` instead of `test_contract.py`**

`pdd test` avoids overwriting existing files. Remove the old file first:
```bash
rm -f tests/test_contract.py && bash demo.sh --exp-b
```

**Coverage shows R1–R4 as `unchecked`**

The generated tests may lack R# markers. Check `tests/test_contract.py` for
`R1`, `R2`, `R3`, `R4` in function names or `# Covers: R#` comments.
The user story provides `story-only` coverage as a fallback.
