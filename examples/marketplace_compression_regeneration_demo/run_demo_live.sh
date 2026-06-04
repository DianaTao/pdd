#!/usr/bin/env bash
# Real PDD Cloud + LLM benchmark (not mocked). Requires: pdd auth login
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "Running marketplace regeneration demo against REAL PDD Cloud (live LLM)."
echo "Ensure you are logged in: pdd auth status"
exec python examples/marketplace_compression_regeneration_demo/run_demo.py --live "$@"
