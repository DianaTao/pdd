#!/usr/bin/env bash
# End-to-end checkup gate showcase for dev unit ``refund`` (issue #833 / PR #1260).
#
# Only prompts/refund_python.prompt is hand-crafted. This script uses PDD to
# generate code, tests, examples, and stories, then runs checkup commands.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PDD_FORCE="${PDD_FORCE:-1}"

if [[ ! -f prompts/refund_python.prompt ]]; then
  echo "Missing hand-crafted prompt: prompts/refund_python.prompt" >&2
  exit 1
fi

if [[ "${CLEAN:-0}" == "1" ]]; then
  echo "==> Cleaning prior generated artifacts"
  rm -rf src/* tests/* examples/* user_stories/* .pdd 2>/dev/null || true
fi

echo "==> 1/4  pdd sync refund --evidence"
echo "     (generates src/, tests/, examples/, user_stories/ from the prompt)"
set +e
pdd sync refund --evidence
SYNC_RC=$?
set -e
if [[ "$SYNC_RC" -ne 0 ]]; then
  echo ""
  echo "Sync exited $SYNC_RC (continuing to contract/coverage/gate for audit output)."
fi

echo ""
echo "==> 2/4  pdd checkup contract check prompts/"
set +e
pdd checkup contract check prompts/
CONTRACT_RC=$?
set -e

echo ""
echo "==> 3/4  pdd checkup coverage prompts/"
set +e
pdd checkup coverage prompts/
COV_RC=$?
set -e
if [[ "$COV_RC" -ne 0 ]]; then
  echo "Coverage exited $COV_RC (continuing; test-only rules are advisory)."
fi

echo ""
echo "==> 4/4  pdd checkup gate refund --json"
set +e
pdd checkup gate refund --json
GATE_RC=$?
set -e

echo ""
echo "Demo complete. Generated artifacts:"
ls -la src/ tests/ examples/ user_stories/ .pdd/evidence/devunits/refund.latest.json 2>/dev/null || true

if [[ "$GATE_RC" -ne 0 ]]; then
  echo ""
  echo "Gate exited $GATE_RC (expected when sync failed or stories/verify/tests"
  echo "are not all recorded as pass on refund.latest.json)."
  echo "Offline failure-code demo: ./demo_failed_sync_gate.py"
  echo "Manual test plan: ./MANUAL_TESTS.md"
fi
