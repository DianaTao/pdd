# Grounding evidence demo (#827)

Offline, human-runnable checks for `generation.grounding` provenance and policy
evaluation. No cloud API keys required.

## Quick demo script

From the repository root:

```bash
python examples/grounding_evidence_demo/run_demo.py
```

The script prints:

1. `examplesUsed` id/title cloud shape mapped into `selected_examples`
2. A sample evidence `generation.grounding` block
3. `grounding_policy.check()` results for satisfied vs missing-review cases

## CLI smoke (uses repo fixtures)

Map cloud id/title into evidence-shaped JSON:

```bash
cd /path/to/pdd
PYTHONPATH=. python -c "
from pdd.grounding_provenance import selected_examples_from_cloud
import json
print(json.dumps(selected_examples_from_cloud(
    [{'id': 'payments', 'title': 'Payments example'}]
), indent=2))
"
```

Pre-generation review + manifest reviewed flag (pinned example):

```bash
PYTHONPATH=. pytest -q \
  tests/test_grounding_provenance.py::test_selected_examples_from_cloud_preserves_id_title_shape \
  tests/test_grounding_test_plan.py::test_generate_review_examples_records_reviewed_in_evidence \
  tests/test_grounding_test_plan.py::test_cloud_id_title_selected_examples_not_empty
```

Full #827 regression gate:

```bash
PYTHONPATH=. pytest -q \
  tests/test_grounding_provenance.py \
  tests/test_grounding_test_plan.py \
  tests/test_grounding_policy.py \
  tests/test_grounding_generate_evidence.py \
  tests/test_llm_invoke_grounding.py \
  tests/commands/test_evidence.py \
  tests/test_evidence_manifest.py
```

## Cloud generate (optional)

Requires auth and uses real `generateCode`:

```bash
pdd generate examples/grounding_evidence_demo/prompts/payments_python.prompt \
  --output examples/grounding_evidence_demo/src/payments.py \
  --evidence --review-examples
```

Inspect `.pdd/evidence/devunits/payments.latest.json` → `generation.grounding`.
