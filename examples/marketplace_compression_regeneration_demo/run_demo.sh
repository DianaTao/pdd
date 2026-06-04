#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec python examples/marketplace_compression_regeneration_demo/run_demo.py "$@"
