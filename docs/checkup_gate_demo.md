# Checkup gate demo (`pdd checkup gate`)

Demonstrates the **evidence policy gate** from [PR #1260](https://github.com/promptdriven/pdd/pull/1260),
part of the [language-complete PDD epic (#833)](https://github.com/promptdriven/pdd/issues/833).

## Branch

Use **`demo/checkup-gate-showcase`** (demo + docs) or **`feat/issue-825-gate`** / PR #1260 (gate implementation only).

```bash
git fetch origin
git checkout demo/checkup-gate-showcase
pip install -e ".[dev]"
export PDD_FORCE=1
```

On `main`, `pdd checkup gate` is not available until PR #1260 merges.

## Automated demo (recommended)

```bash
python examples/checkup_gate_example.py
```

Runs six scenarios via `run_gate_policy` (no API keys, no LLM) and prints equivalent CLI commands.

## Agent prompt

Copy the task file for coding agents:

```text
examples/checkup_gate_demo/agent.prompt
```

## Manual CLI on the fixture tree

```bash
# Prepare a passing manifest (example script does this in a temp dir; for CLI demo:
cd examples/checkup_gate_demo
python -c "
from pathlib import Path
import sys
sys.path.insert(0, '../..')
from examples.checkup_gate_demo.manifests import write_demo_manifest
from pdd.evidence_store import sha256_file
code = Path('src/refund.py')
write_demo_manifest(
    Path('.pdd/evidence/devunits/refund.latest.json'),
    basename='refund',
    output_rel='src/refund.py',
    output_hash=sha256_file(code),
    validation={'detect_stories':'pass','verify':'pass','unit_tests':'pass'},
)
"

pdd checkup gate refund --json
echo '# stale' >> src/refund.py
pdd checkup gate refund --json
```

## Scenarios covered

| # | Scenario | Expected failure codes |
|---|----------|------------------------|
| 1 | Empty project | `no_manifests` |
| 2 | Generate-only evidence | `*_not_available` |
| 3 | Fresh pass manifest | *(none)* |
| 4 | Edited output file | `stale_output` |
| 5 | Sync skip flags, default policy | `skipped_verify`, `skipped_tests` |
| 6 | Same manifest + permissive policy | *(none)* |

## Related commands (issue #833 stack)

```bash
pdd sync refund --evidence          # produce .pdd/evidence/devunits/refund.latest.json
pdd checkup contract check prompts/
pdd checkup coverage prompts/
pdd checkup gate refund --json      # enforce evidence policy
```

## Tests

```bash
pytest -vv tests/test_checkup_gate_demo.py tests/test_gate_main.py
```
