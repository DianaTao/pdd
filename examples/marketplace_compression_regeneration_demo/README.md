# Marketplace compression regeneration demo

Reproducible benchmark for [promptdriven/pdd#876](https://github.com/promptdriven/pdd/issues/876): **compressed marketplace few-shot context must still support regeneration**.

## Mocked vs real (read this first)

| Command | LLM | PDD Cloud HTTP | Marketplace few-shot |
|---------|-----|----------------|----------------------|
| `python .../run_demo.py` (**default**) | **Mocked** (fixed code from mold) | **Mocked** (`requests.post` stub) | Built from local fixtures in the stub |
| `python .../run_demo.py --live` | **Real** cloud model | **Real** `generateCode` / `llmInvoke` | **Real** cloud `examplesUsed` selection |
| `prompt_compression_few_shot_demo` | **None** (preprocess only) | **None** | N/A |

**For a real cloud + LLM benchmark, use `--live`:**

```bash
pdd auth logout && pdd auth login   # refresh if you see "Token expired"
bash examples/marketplace_compression_regeneration_demo/run_demo_live.sh
```

**Live marketplace validation (default):** `--live` seeds catalog fixtures via `submitExample`, pins `marketplace/ticket-classifier-*` slugs, and **fails** unless cloud `examplesUsed` has `source: marketplace` or resolves those catalog pins. Placeholder env values like `slug/from/your/cloud` are ignored.

```bash
pdd auth login
python examples/marketplace_compression_regeneration_demo/run_demo.py --live
```

Override pins with real marketplace slugs from your library:

```bash
export PDD_MARKETPLACE_DEMO_PIN_MODULES="your/marketplace-module-slug,another/slug"
python examples/marketplace_compression_regeneration_demo/run_demo.py --live
```

If your tenant cannot return marketplace-tagged examples, use the **representative** run (fully satisfies the #876 regeneration benchmark in CI) or pass `--allow-non-marketplace` for a real-model run that still reports fixture marketplace few-shot compression sizes.

Default mode exists for CI (`pytest`); it does **not** call OpenAI/Gemini or live PDD Cloud.

See also [`examples/BENCHMARK_876.md`](../BENCHMARK_876.md) for the full review mapping.

## Fixture marketplace examples (not synthetic prose only)

| Module | Files |
|--------|--------|
| `marketplace/ticket-classifier-bug` | `fixtures/marketplace/ticket-classifier-bug.{prompt,py}` |
| `marketplace/ticket-classifier-docs` | `fixtures/marketplace/ticket-classifier-docs.{prompt,py}` |

`fixtures/marketplace_examples.json` lists cloud-shaped `examplesUsed` records (`source: marketplace`, hashes, similarity).

Compressed few-shot **code** in the stub uses `apply_compressed_include_with_fallback()` on those `.py` files (same #876 compression path as the CLI). Compressed few-shot **prompt** text drops provenance-only “Creator notes” while keeping Input/Output pairs.

Generated module body comes from `fixtures/ticket_classifier_mold.py` (local mold aligned with the task prompt).

## Representative mode (CI / default)

Stubs `requests.post` for:

- **`generateCode`** — returns mold code + `examplesUsed` + `promptStats` with marketplace few-shot built from fixtures
- **`llmInvoke`** — returns `is_big_change: true` so incremental runs fall back to full generate (re-runnable)

```bash
python examples/marketplace_compression_regeneration_demo/run_demo.py
pytest -q tests/test_marketplace_compression_regeneration_demo.py
```

## Live mode (manual, real PDD Cloud)

```bash
pdd auth login
python examples/marketplace_compression_regeneration_demo/run_demo.py --live
# or: PDD_MARKETPLACE_DEMO_LIVE=1 python examples/marketplace_compression_regeneration_demo/run_demo.py
```

Uses real cloud marketplace selection and a real model. Not run in CI.

## What it verifies

| Criterion | Check |
|-----------|--------|
| Marketplace few-shot selection | `examples_used[].source == "marketplace"` in evidence |
| `pdd generate` regeneration path | Cloud branch + output module written |
| Compression benefit | Smaller `finalPromptChars` / client prompt with `--compress` |
| Behavioral contract | `classify_ticket` / `format_ticket_json` assertions |
| Same catalog both runs | Shared `marketplace_examples.json` records |

Report: `generated/marketplace_compression_report.json` includes `benchmark_criteria` and `execution_mode`.

## Pair with preprocess demo

Preprocess-only contract proof:

```bash
python examples/prompt_compression_few_shot_demo/run_demo.py
```

Combined pytest:

```bash
pytest -q \
  tests/test_prompt_compression_few_shot_demo.py \
  tests/test_marketplace_compression_regeneration_demo.py \
  tests/test_issue_876_compressed_few_shot.py
```
