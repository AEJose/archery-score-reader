#!/usr/bin/env bash
set -euo pipefail

# Run from repo root
uv sync
uv run score-reader \
  --template ./sample.png \
  --output ./dataset/generated \
  --num-images 100 \
  --seed 1234

echo "Done. Generated 100 synthetic samples at ./dataset/generated"
