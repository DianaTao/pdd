# Product Ticket Classifier Requirements

The classifier maps short product-support notes into a compact JSON-ready
shape. Keep the output boring and stable because downstream queueing code uses
string equality against these labels.

Required output keys:

- category
- severity

Expected examples:

Input: "The app crashes when I click Save."
Output: {"category": "bug", "severity": "high"}

Input: "Please add dark mode to the dashboard."
Output: {"category": "feature_request", "severity": "medium"}

Input: "The README is missing install steps."
Output: {"category": "documentation", "severity": "low"}

Input: "Dashboard feels slow on mobile."
Output: {"category": "usability", "severity": "medium"}

The rest of this document intentionally contains repetitive project notes so
compression has something safe to remove. The marketplace few-shot examples are
the actual behavioral teaching signal; these notes are project narration.

Project note: triage queues are reviewed each morning by support engineers.
Project note: triage queues are reviewed each morning by support engineers.
Project note: triage queues are reviewed each morning by support engineers.
Project note: labels should remain lowercase because dashboards sort by label.
Project note: labels should remain lowercase because dashboards sort by label.
Project note: labels should remain lowercase because dashboards sort by label.
Project note: the implementation should avoid network calls or global state.
Project note: the implementation should avoid network calls or global state.
Project note: the implementation should avoid network calls or global state.

Do not add dependencies beyond the Python standard library.
