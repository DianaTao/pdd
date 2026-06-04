# Marketplace compression regeneration demo

This demo is the reproducible touch point for issue #876's regeneration
question: compressed few-shot context must still teach the model enough for
generation to work.

The script drives the normal `pdd generate` command twice:

1. uncompressed marketplace grounding
2. compressed marketplace grounding

To keep the check stable in CI, the network request is replaced with a
representative PDD Cloud marketplace response that includes `examplesUsed`
records with `source: marketplace`. The run still exercises the client-side
cloud generation branch, evidence manifest grounding, generated-file write, and
the behavioral contract for the regenerated module.

## Run

From the repository root:

```bash
python examples/marketplace_compression_regeneration_demo/run_demo.py
```

Focused pytest:

```bash
pytest -q tests/test_marketplace_compression_regeneration_demo.py
```

## What It Verifies

- PDD Cloud marketplace-style `examplesUsed` are recorded in evidence.
- The same representative marketplace selection is used for uncompressed and
  compressed generation.
- Compressed prompt/context sizes are smaller than the uncompressed baseline.
- The regenerated output passes the expected behavior checks:
  - bug -> high
  - feature request -> medium
  - documentation -> low
  - usability JSON output remains stable

The full live cloud benchmark can still be run separately with real
credentials, but this demo keeps the PR's regression proof deterministic.
