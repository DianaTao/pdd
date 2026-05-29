#!/usr/bin/env bash
# Quick CLI smoke checks (no sync, no API). Verifies editable install exposes flags.
set -euo pipefail
DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DEMO"

export PDD_SKIP_UPDATE_CHECK=1
export PDD_AUTO_UPDATE=false
export CI=1

echo "==> which pdd: $(command -v pdd)"
echo "==> pdd version: $(pdd --version 2>/dev/null || true)"

echo ""
echo "==> sync --help must list --evidence"
pdd sync --help | grep -q -- '--evidence'

echo "==> checkup gate --help"
pdd checkup gate --help | grep -q -- '--json'

echo ""
echo "==> no top-level pdd gate"
if pdd gate --help 2>/dev/null; then
  echo "ERROR: unexpected top-level 'pdd gate' command" >&2
  exit 1
fi
echo "    (top-level gate correctly absent)"

echo ""
echo "==> cwd isolation: prompts resolve under demo, not repo root"
python -c "
from pathlib import Path
import pdd.sync_main as sm
# minimal: ensure refund prompt is found from demo cwd
from pdd.sync_determine_operation import get_pdd_file_paths
paths = get_pdd_file_paths('refund', 'python', prompts_dir='prompts')
assert paths['prompt'].is_file(), paths
print('    refund prompt:', paths['prompt'])
"

echo ""
echo "CLI smoke checks passed."
