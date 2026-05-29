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
pdd sync refund --evidence

echo ""
echo "==> 2/4  pdd checkup contract check prompts/"
pdd checkup contract check prompts/

echo ""
echo "==> 3/4  pdd checkup coverage prompts/"
pdd checkup coverage prompts/

echo ""
echo "==> 4/4  pdd checkup gate refund --json"
pdd checkup gate refund --json

echo ""
echo "Demo complete. Generated artifacts:"
ls -la src/ tests/ examples/ user_stories/ .pdd/evidence/devunits/refund.latest.json 2>/dev/null || true
