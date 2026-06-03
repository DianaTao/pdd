# Prompt compression few-shot demo

This demo shows how PDD prompt compression shortens redundant context while
preserving **few-shot behavioral contracts**.

## What are few-shot examples?

Few-shot examples are small input/output pairs embedded in a prompt that teach
an LLM the expected format, tone, schema, and reasoning pattern. In this demo
they look like:

```text
Input: "The app crashes when I click Save."
Output: {"category": "bug", "severity": "high"}
```

Python grounding molds (`<include mode="compressed">`) are also few-shot
examples: they show executable patterns the model should follow.

## Why they matter for compression

Compression must not silently delete or corrupt few-shot examples. Losing them
changes model behavior even when the task description still looks correct.

## What is safe to compress

- Redundant narrative background and repeated onboarding notes
- Docstrings and comment-only lines in Python few-shot includes
- Non-contract prose in `.md` files when using `mode="contracts"`

## What should usually be preserved

- Few-shot example inputs and outputs in the prompt body
- Required output schemas and hard constraints
- Executable logic in Python few-shot molds
- Grounding/provenance metadata (`<pdd-interface>`, evidence manifests)

## Run the demo

From the repository root:

```bash
python examples/prompt_compression_few_shot_demo/run_demo.py
```

Or:

```bash
bash examples/prompt_compression_few_shot_demo/run_demo.sh
```

Run the focused pytest:

```bash
pytest -q tests/test_prompt_compression_few_shot_demo.py
```

## What the demo verifies

1. Expanded baseline (`compress=False`) is longer than expanded compressed output
2. All four few-shot Input/Output pairs remain in the expanded prompt
3. The JSON output schema block remains intact
4. The compressed Python include keeps `classify_issue` / `format_issue_json` bodies
5. Docstrings and redundant markdown anecdotes are removed
6. `<pdd-interface>` grounding metadata survives contracts compression
7. Repeated runs produce identical compressed output (deterministic)
