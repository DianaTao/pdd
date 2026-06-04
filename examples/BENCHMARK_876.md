# Issue #876 benchmark touch points

Reproducible demos for [promptdriven/pdd#876](https://github.com/promptdriven/pdd/issues/876) compressed marketplace few-shot context.

## Review questions mapped to demos

| Question | Demo | CI command |
|----------|------|------------|
| Does compression preserve few-shot contracts in expanded prompts? | [`prompt_compression_few_shot_demo/`](prompt_compression_few_shot_demo/) | `python examples/prompt_compression_few_shot_demo/run_demo.py` |
| Does compressed marketplace few-shot still support regeneration? | [`marketplace_compression_regeneration_demo/`](marketplace_compression_regeneration_demo/) | `python examples/marketplace_compression_regeneration_demo/run_demo.py` |
| Unit/regression coverage for compression wiring | `tests/test_issue_876_compressed_few_shot.py` | `pytest -q tests/test_issue_876_compressed_few_shot.py` |

Combined regression (preprocess + regeneration representative path):

```bash
pytest -q \
  tests/test_prompt_compression_few_shot_demo.py \
  tests/test_marketplace_compression_regeneration_demo.py \
  tests/test_issue_876_compressed_few_shot.py
```

## What each demo proves

### 1. Preprocess few-shot demo (local, deterministic)

- Expands `classify_issues.prompt` with and without `PDD_CONTEXT_COMPRESSION=contracts`.
- **Preserves:** four Input/Output pairs, JSON schema, Python mold bodies, `<pdd-interface>`.
- **Compresses:** docstrings, redundant markdown, comment-only lines.
- Reports char reduction and SHA-256 of compressed output.

Does **not** call `pdd generate` or PDD Cloud.

### 2. Marketplace regeneration demo (representative cloud path)

- Runs **`pdd generate` twice** on the same prompt: without `--compress`, then with `--compress`.
- Uses **fixture marketplace records** (`source: marketplace`) shaped like cloud `examplesUsed`.
- Builds injected few-shot text from those fixture files; **compressed** few-shot uses PDD `apply_compressed_include_with_fallback()` on marketplace `.py` files (same code path as #876).
- Exercises: cloud `generateCode` payload, evidence manifest grounding, written output module, behavior contract checks.
- Reports client prompt size, cloud `promptStats`, expanded prompt size, and reduction.

**CI mode:** stubs `requests.post` for `generateCode` and `llmInvoke` (incremental fallback) so no live API keys are required.

**Live mode:** optional manual run against real PDD Cloud (see marketplace demo README).

### 3. Live cloud benchmark (manual, optional)

```bash
pdd auth login
python examples/marketplace_compression_regeneration_demo/run_demo.py --live
```

Uses real PDD Cloud + model. By default seeds catalog fixtures, pins catalog slugs, and
requires `source: marketplace` (or `--allow-non-marketplace`). Also reports
`fixture_marketplace_few_shot` sizes from the local #876 compress path. Not run in CI.

## Expected representative regeneration results

After `run_demo.py` (stub mode), see `generated/marketplace_compression_report.json`:

- `runs[].examples_used[].source` == `"marketplace"`
- `reduction.final_prompt_chars` > 0
- `runs[].behavior_passed` == true
- Compressed `finalPromptChars` < uncompressed
