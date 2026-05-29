#!/usr/bin/env bash
# Offline-safe manual verification for pdd checkup drift (PR #1261).
# No LLM calls — uses --dry-run only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${ROOT}/workspace"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
CODE_FILE="refund_demo/refund_payment.py"
export PDD_SKIP_UPDATE_CHECK=1

echo "== checkup drift manual demo =="
echo "Demo dir:    ${ROOT}"
echo "Workspace:   ${WORKSPACE}"
echo "Repo root:   ${REPO_ROOT}"
echo

if ! python -c "import pdd.cli" 2>/dev/null; then
  echo "ERROR: editable pdd not installed. From repo root on feat/issue-831-drift:"
  echo "  conda activate pdd && pip install -e ."
  exit 1
fi

cd "${WORKSPACE}"
# A leftover workspace/pdd/ directory shadows the installed CLI when cwd is here.
rm -rf pdd

BASELINE_HASH="$(shasum -a 256 "${CODE_FILE}" | awk '{print $1}')"
echo "== 1/4 Baseline pytest =="
python -m pytest -q tests/test_refund_payment.py
echo

echo "== 2/4 Drift dry-run (JSON) =="
python -m pdd checkup drift refund_payment --code-file "${CODE_FILE}" --dry-run --json 2>/dev/null | tee /tmp/drift_demo_dry_run.json
python3 -c "
import json
raw = open('/tmp/drift_demo_dry_run.json').read()
start = raw.index('{')
d, _ = json.JSONDecoder().raw_decode(raw, start)
assert d['status'] == 'stable', d
assert d['public_api_unchanged'] is True, d
assert d['dry_run'] is True, d
print('OK: status=stable, public_api_unchanged=true')
"
echo

echo "== 3/4 Drift from evidence (JSON) =="
python -m pdd checkup drift refund_payment \
  --from-evidence .pdd/evidence/devunits/refund_payment.latest.json \
  --code-file "${CODE_FILE}" \
  --dry-run --json 2>/dev/null | tee /tmp/drift_demo_evidence.json
python3 -c "
import json
raw = open('/tmp/drift_demo_evidence.json').read()
start = raw.index('{')
d, _ = json.JSONDecoder().raw_decode(raw, start)
assert d['policy_check_skipped'] is True, d
assert d['policy_check_unavailable'] is False, d
assert d['status'] == 'stable', d
print('OK: evidence manifest does not force policy gate')
"
echo

echo "== 4/4 Worktree unchanged =="
AFTER_HASH="$(shasum -a 256 "${CODE_FILE}" | awk '{print $1}')"
if [[ "${BASELINE_HASH}" != "${AFTER_HASH}" ]]; then
  echo "FAIL: ${CODE_FILE} was modified"
  exit 1
fi
echo "OK: baseline file hash unchanged (${BASELINE_HASH})"
echo
echo "All offline checks passed."
echo "Optional LLM regeneration: see RUN.md Phase 2."
