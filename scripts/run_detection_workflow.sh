#!/usr/bin/env bash
set -euo pipefail

# Workflow:
# 1) optionally generate synthetic dataset
# 2) run baseline detector (oracle/noisy)
# 3) output detection metrics json

OUTPUT_DIR="${OUTPUT_DIR:-./dataset/eval_run}"
TEMPLATE="${TEMPLATE:-./sample.png}"
NUM_IMAGES="${NUM_IMAGES:-100}"
SEED="${SEED:-1234}"
DETECT_MODE="${DETECT_MODE:-noisy}"      # noisy | oracle
ERROR_RATE="${ERROR_RATE:-0.10}"
MANIFEST="${MANIFEST:-}"

if [[ -z "$MANIFEST" ]]; then
  echo "[1/3] Generate synthetic dataset..."
  uv run score-reader generate-dataset \
    --output "$OUTPUT_DIR" \
    --template "$TEMPLATE" \
    --num-images "$NUM_IMAGES" \
    --seed "$SEED"
  MANIFEST="$OUTPUT_DIR/manifest.jsonl"
else
  echo "[1/3] Reuse existing manifest: $MANIFEST"
fi

echo "[2/3] Run detection evaluation..."
uv run python - <<'PY'
from pathlib import Path
import os
from score_reader.dataset.evaluation import BaselineDetector, evaluate_dataset

manifest = Path(os.environ["MANIFEST"])
out_dir = Path(os.environ["OUTPUT_DIR"]) / "eval"
mode = os.environ["DETECT_MODE"]
error_rate = float(os.environ["ERROR_RATE"])
seed = int(os.environ["SEED"])

path = evaluate_dataset(
    manifest_path=manifest,
    output_dir=out_dir,
    detector=BaselineDetector(mode=mode, error_rate=error_rate, seed=seed),
)
print(f"Evaluation result written to: {path}")
PY

echo "[3/3] Done."
cat "$OUTPUT_DIR/eval/detection_eval.json"
