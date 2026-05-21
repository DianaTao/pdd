# `pdd contracts drift`

Detect when code has drifted from the prompt's contract rules.

`pdd coverage --contracts` answers "do tests reference R1?".
`pdd contracts drift` answers "does the code actually implement R1?".
These are different questions.

## Check types

### Structural (default, deterministic)

Scans code for identifiers referenced in MUST NOT clauses.
E.g. `MUST NOT call cache_client` → searches for `cache_client` in the code file.

- Safe for CI: no LLM, fully deterministic.
- Exits non-zero only with `--strict`.

### Semantic (--semantic, LLM, advisory)

Asks an LLM whether each MUST obligation appears to be implemented.
Always advisory — never a hard CI gate — unless `--strict` is also passed.

## Usage

```bash
pdd contracts drift prompts/foo_python.prompt pdd/foo.py
pdd contracts drift --semantic prompts/foo_python.prompt pdd/foo.py
pdd contracts drift --strict prompts/foo_python.prompt pdd/foo.py
pdd contracts drift --json prompts/foo_python.prompt pdd/foo.py
```

Auto-detection: if the code file argument is omitted, the command tries to locate
`pdd/<stem>.py` or `src/<stem>.py` from the prompt filename.

## Options

| Flag | Description |
|------|-------------|
| `--semantic` | Run LLM semantic check in addition to structural |
| `--strict` | Exit non-zero on any structural finding |
| `--json` | Output findings as JSON |

## Output

```
prompts/foo_python.prompt ↔ pdd/foo.py  2 finding(s)
  structural  R2  cache_client  Rule R2 says MUST NOT call 'cache_client' …
    line 47: result = cache_client.fetch(key)
  semantic    R3  medium  Rule R3 says MUST raise ValueError for … but code returns None.
```

## JSON output

```json
{
  "prompt_path": "prompts/foo_python.prompt",
  "code_path": "pdd/foo.py",
  "has_drift": true,
  "finding_count": 1,
  "structural_findings": [
    {
      "kind": "structural",
      "rule_id": "R2",
      "message": "Rule R2 says MUST NOT use 'cache_client' but it appears in code at line 47.",
      "term": "cache_client",
      "line": "    result = cache_client.fetch(key)",
      "line_number": 47,
      "confidence": "medium"
    }
  ],
  "semantic_findings": []
}
```

## Limitations

- Structural check only detects MUST NOT clauses with explicit identifiers.
- Semantic check uses a single LLM pass; confidence may be medium/low for
  complex logic. Always verify semantic findings manually.
- Neither check proves full correctness; use in addition to tests, not instead.

## Related commands

- `pdd contracts gate` — deterministic CI gate (structural check is part of compile stage)
- `pdd evidence emit` — shows what evidence exists for each rule
- `pdd coverage --contracts` — shows coverage status
