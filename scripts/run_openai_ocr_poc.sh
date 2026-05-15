#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <image_or_folder> [output_csv] [output_json] [model]"
  exit 1
fi

INPUT_PATH="$1"
OUTPUT_CSV="${2:-./out/openai_ocr.csv}"
OUTPUT_JSON="${3:-./out/openai_ocr.json}"
MODEL="${4:-gpt-5.5}"

uv run python -m score_reader.openai_poc extract \
  --input-path "$INPUT_PATH" \
  --output-csv "$OUTPUT_CSV" \
  --output-json "$OUTPUT_JSON" \
  --model "$MODEL"
