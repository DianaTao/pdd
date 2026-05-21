# `pdd contracts gate`

Single deterministic CI gate — runs the full contract pipeline in one command.
**Zero LLM calls.** This is what goes in `.github/workflows/`.

## Purpose

Without a gate, the prompt-as-source-of-truth system is a collection of tools
developers run manually.  `pdd contracts gate` makes it **enforceable in CI**.

## Usage

```bash
pdd contracts gate prompts/foo_python.prompt
pdd contracts gate --strict --stories-dir user_stories/ prompts/
pdd contracts gate --json prompts/foo_python.prompt
```

## Stages

| # | Stage | What it checks |
|---|-------|----------------|
| 1 | `prompt-lint` | Deterministic lint only — vague terms, missing modals, structural issues. **No LLM.** |
| 2 | `contracts-check` | Structural authoring defects in `<contract_rules>`, `<vocabulary>`, `<coverage>`. |
| 3 | `contracts-compile` | Each rule compiles into a stable IR with observable obligations. |
| 4 | `coverage` | Every MUST/MUST NOT rule is linked to at least a story or test. |

Stages run in order.  If a stage exits with code 2 (error), subsequent stages
are **skipped** (fail-fast).

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All stages pass |
| 1 | Warnings (no errors) |
| 2 | One or more errors |

## Key invariant

Stage 1 (`prompt-lint`) **must not** call the LLM.  It runs the same deterministic
rules as `pdd prompt lint` without `--ambiguity`.  If the gate ever called an LLM
it would become flaky and slow, and teams would disable it.

## Output

Default (rich table):

```
 pass  prompt-lint        errors=0 warns=0
 pass  contracts-check    errors=0 warns=0
 pass  contracts-compile  rules=3 errors=0
 warn  coverage           total=3 checked=2 unchecked=1
  exit 1
```

With `--json`:

```json
{
  "target": "prompts/foo_python.prompt",
  "exit_code": 1,
  "stages": [
    {"name": "prompt-lint", "exit_code": 0, "error_count": 0, "warn_count": 0, "detail": "errors=0 warns=0", "skipped": false},
    ...
  ]
}
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--stories-dir DIR` | none | User-stories directory for lint + coverage |
| `--tests-dir DIR` | none | Tests directory for coverage |
| `--strict` | false | Unchecked coverage rules → exit 2 instead of 1 |
| `--skip-stories-lint` | false | Skip story scanning in stage 1 (faster) |
| `--json` | false | Machine-readable output |

## CI workflow example

```yaml
- name: Contract gate
  run: pdd contracts gate --strict --stories-dir user_stories/ prompts/
```

## Related commands

- `pdd prompt lint` — individual lint stage
- `pdd contracts check` — individual check stage
- `pdd contracts compile` — individual compile stage
- `pdd coverage --contracts` — individual coverage stage
- `pdd evidence emit` — detailed per-rule evidence report
