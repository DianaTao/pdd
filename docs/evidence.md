# `pdd evidence`

Per-rule evidence reporting for prompt contracts.  Deterministic, no LLM.

Complements `pdd coverage --contracts` (which shows status counts) by showing
the **content** of the evidence: story acceptance-criteria snippets, test function
names, and formalization predicate text.  Most useful for PR comments and onboarding.

## Subcommands

| Subcommand | What it does |
|------------|-------------|
| `pdd evidence emit` | Build and display a manifest; optionally write JSON |
| `pdd evidence validate` | Validate a stored manifest JSON file |
| `pdd evidence show` | Display a previously emitted manifest |

## `pdd evidence emit`

```bash
pdd evidence emit prompts/foo_python.prompt
pdd evidence emit --gap-only prompts/foo_python.prompt
pdd evidence emit --json prompts/foo_python.prompt
pdd evidence emit --markdown prompts/foo_python.prompt          # for PR comments
pdd evidence emit --output reports/evidence.json prompts/foo_python.prompt
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--stories-dir DIR` | none | Story directory for AC snippets |
| `--tests-dir DIR` | none | Tests directory |
| `--output PATH` | none | Write manifest JSON to file |
| `--json` | false | Print manifest JSON to stdout |
| `--gap-only` | false | Only show rules with evidence gaps |
| `--markdown` | false | Output markdown suitable for PR comments |

### Manifest schema

```json
{
  "schema": "pdd.evidence.manifest.v1",
  "generated_at": "2026-05-21T…",
  "prompt_path": "prompts/foo_python.prompt",
  "prompt_sha256": "…",
  "rule_count": 3,
  "gap_count": 1,
  "rules": [
    {
      "rule_id": "R1",
      "status": "checked",
      "stories": ["story__foo.md"],
      "story_snippets": ["Given amount_cents = 0, the service MUST return HTTP 400…"],
      "tests": ["test_R1_rejects_zero_refund"],
      "formal": [],
      "waiver": null,
      "gap": false
    }
  ]
}
```

## `pdd evidence validate`

```bash
pdd evidence validate reports/evidence.json
pdd evidence validate --json reports/evidence.json
```

Exits 2 if the manifest is invalid (wrong schema, missing required keys).

## `pdd evidence show`

```bash
pdd evidence show reports/evidence.json
pdd evidence show --gap-only reports/evidence.json
pdd evidence show --markdown reports/evidence.json
```

Displays a previously written manifest file without re-scanning.

## Difference from `pdd coverage --contracts`

| | `pdd coverage --contracts` | `pdd evidence emit` |
|-|---------------------------|---------------------|
| Shows per-rule status | ✅ | ✅ |
| Shows story text snippets | ❌ | ✅ |
| Shows test function names | ❌ | ✅ |
| Shows formalization predicates | ❌ | ✅ |
| `--markdown` for PR comments | ❌ | ✅ |
| Writes a manifest file | ❌ | ✅ (`--output`) |
| Validates a stored manifest | ❌ | ✅ (`validate`) |

## CI use

```yaml
- name: Emit evidence manifest
  run: pdd evidence emit --output reports/evidence.json prompts/foo_python.prompt

- name: Validate evidence manifest
  run: pdd evidence validate reports/evidence.json
```

## Related commands

- `pdd contracts gate` — deterministic CI gate (includes coverage stage)
- `pdd coverage --contracts` — status matrix only
