#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python examples/prompt_compression_few_shot_demo/run_demo.py
