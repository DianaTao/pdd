#!/usr/bin/env bash
# Offline checks for the checkup gate demo (no API keys, no pdd sync).
#
# Run from anywhere:
#   ./examples/checkup_gate_demo/run_offline_checks.sh
# Or:
#   cd examples/checkup_gate_demo && ./run_offline_checks.sh
set -euo pipefail
DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$DEMO/../.." && pwd)"
cd "$DEMO"

export PDD_SKIP_UPDATE_CHECK=1
export PDD_AUTO_UPDATE=false
export CI=1

echo "==> Repo: $REPO"
echo "==> Demo: $DEMO"
echo ""

echo "==> 1/4  Fixture tree"
test -f prompts/refund_python.prompt
test -f .pddrc
test -f .pdd/policy-permissive.yml
test -f agent.prompt
echo "    OK"

echo ""
echo "==> 2/4  pytest (demo + gate unit tests)"
cd "$REPO"
python -m pytest -vv tests/test_checkup_gate_demo.py tests/test_gate_main.py tests/test_gate_failed_sync.py
cd "$DEMO"

echo ""
echo "==> 3/4  Offline gate scenarios (examples/checkup_gate_example.py)"
python "$REPO/examples/checkup_gate_example.py"

echo ""
echo "==> 4/4  Gate on a failed-sync-shaped manifest (no LLM)"
python "$DEMO/demo_failed_sync_gate.py"

echo ""
echo "All offline checks passed."
