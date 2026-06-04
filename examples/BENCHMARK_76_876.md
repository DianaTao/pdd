# Issues #76 + #876: compressed sync context and marketplace regeneration

This branch (`demo/compression-sync-marketplace`) combines:

- **#876** — marketplace few-shot compression on `pdd generate` ([`marketplace_compression_regeneration_demo/`](marketplace_compression_regeneration_demo/))
- **#76** — phase-aware **compressed sync context** on `pdd sync` generate / verify / test / fix ([`compressed_sync_context.py`](../pdd/compressed_sync_context.py))

The review bar from [#876](https://github.com/promptdriven/pdd/issues/876) is: compression must preserve enough context for **regeneration**, not only preprocess fidelity. The #76 bar is the same for the **full sync loop** with real marketplace grounding.

## Quick matrix

| Question | CI (no API keys) | Manual cloud (human-verifiable) |
|----------|------------------|----------------------------------|
| Preprocess preserves few-shot pairs/schema/mold? | `python examples/prompt_compression_few_shot_demo/run_demo.py` | same |
| `pdd generate` + marketplace few-shot still regenerates? | `python examples/marketplace_compression_regeneration_demo/run_demo.py` | `bash examples/marketplace_compression_regeneration_demo/run_demo_live.sh` |
| Compressed sync packages built for generate/verify/fix? | `python examples/marketplace_compression_regeneration_demo/run_sync_compressed_touchpoint.py` | `python examples/marketplace_compression_regeneration_demo/run_sync_compressed_touchpoint.py --live` |
| Orchestration passes `compressed_context` through phases? | `pytest -q tests/test_sync_orchestration.py::test_compressed_context_generate_verify_fix_loop_records_phase_metadata` | inspect `.pdd/evidence/runs/*.json` → `generation.compression` after live sync |

## 1. Marketplace generate benchmark (#876) — already on integration branch

```bash
# Representative (CI)
python examples/marketplace_compression_regeneration_demo/run_demo.py
pytest -q tests/test_marketplace_compression_regeneration_demo.py

# Live PDD Cloud + model
pdd auth login
bash examples/marketplace_compression_regeneration_demo/run_demo_live.sh
```

Report: `examples/marketplace_compression_regeneration_demo/generated/marketplace_compression_report.json`

Check:

- `runs[].examples_used[].source == "marketplace"`
- `runs[].behavior_passed == true`
- compressed `finalPromptChars` < uncompressed

## 2. Compressed sync context touchpoint (#76)

Local phase packages (no LLM):

```bash
python examples/marketplace_compression_regeneration_demo/run_sync_compressed_touchpoint.py
pytest -q tests/test_sync_compressed_context_marketplace_touchpoint.py
```

Writes `generated/sync_compressed_context_report.json` with per-phase `estimated_tokens`, `compressed_sha256`, and `used` flags.

### Live sync + cloud marketplace (human-verifiable)

From the demo directory, with JWT and a model configured:

```bash
cd examples/marketplace_compression_regeneration_demo
pdd auth login

# A) Known-good generate path (marketplace few-shot only)
python run_demo.py --live

# B) Full sync with compressed phase context + example compression
python run_sync_compressed_touchpoint.py --live
```

`--live` sync runs `pdd sync ticket_classifier` twice when possible:

1. `--no-compressed-context` (baseline)
2. `--compressed-context --compress --compress-examples` (treatment)

After each run, open the newest evidence run under `.pdd/evidence/runs/` and confirm:

```json
"generation": {
  "compression": {
    "mode": "compressed-sync-context",
    "requested": true,
    "used": true,
    "phases": ["generate", "verify", "fix"]
  },
  "grounding": { "examples": [ { "source": "marketplace", ... } ] }
}
```

Also confirm generated code still passes the behavior checks in `run_demo.py` (`classify_ticket` / `format_ticket_json`).

## 3. Combined CI regression

```bash
pytest -q \
  tests/test_prompt_compression_few_shot_demo.py \
  tests/test_marketplace_compression_regeneration_demo.py \
  tests/test_issue_876_compressed_few_shot.py \
  tests/test_sync_compressed_context_marketplace_touchpoint.py \
  tests/test_compressed_sync_context.py \
  tests/test_sync_orchestration.py::test_compressed_context_generate_verify_fix_loop_records_phase_metadata
```

## Branch setup (maintainers)

```bash
git fetch fork integration/issue-72-67-73-compression-demo change/issue-76
git checkout -b demo/compression-sync-marketplace fork/integration/issue-72-67-73-compression-demo
git merge change/issue-76   # resolve conflicts; keep both context_compression CLI and compressed_sync_context
```

Push to your fork when ready:

```bash
git push -u fork demo/compression-sync-marketplace
```
