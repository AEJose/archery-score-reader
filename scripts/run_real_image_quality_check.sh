#!/usr/bin/env bash
set -euo pipefail

IMAGES_DIR="${IMAGES_DIR:-./dataset/real_images}"
OUTPUT_JSON="${OUTPUT_JSON:-./dataset/real_images_quality/quality_report.json}"

echo "Analyze image quality in: $IMAGES_DIR"
uv run python - <<'PY'
import os
from pathlib import Path
from score_reader.dataset.image_quality import analyze_folder

images_dir = Path(os.environ["IMAGES_DIR"])
out = Path(os.environ["OUTPUT_JSON"])
path = analyze_folder(images_dir, out)
print(f"Quality report written to: {path}")
PY

cat "$OUTPUT_JSON"
