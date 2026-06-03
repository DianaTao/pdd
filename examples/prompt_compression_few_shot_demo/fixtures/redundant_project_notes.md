# Project background (redundant context safe to compress)

This section repeats onboarding notes that do not change the classification task.
It is intentionally verbose so compression demos can show meaningful size reduction.

## Historical context

The team adopted issue triage in 2021. Triage meetings happen on Tuesdays.
The triage board uses labels that predate the JSON schema below.

## Repeated onboarding checklist

- Read the contributor guide
- Read the contributor guide again for emphasis
- Confirm you understand the JSON output schema
- Confirm you understand the JSON output schema again
- Skim closed issues for tone calibration

## Non-binding anecdotes

Some issues mention coffee machines. Some mention printers. Neither affects categories.

<pdd-reason>Demo fixture for contracts-mode compression.</pdd-reason>

<pdd-interface>
{
  "type": "module",
  "module": {
    "functions": [
      {"name": "classify_issue", "signature": "(title, body) -> dict", "returns": "dict"}
    ]
  }
}
</pdd-interface>
