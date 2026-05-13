# Synthetic Data Generation Logic

This document explains how `archery-score-reader` generates synthetic score-sheet images and labels.

## End-to-end flow

The generation pipeline is implemented in `DatasetPipeline`:

1. Initialize deterministic random generator using a base seed.
2. For each output image:
   - generate 4 synthetic targets (one per athlete block),
   - render values onto a template score sheet,
   - write label JSON,
   - append one line to `manifest.jsonl`.

Output structure:

- `images/train/synthetic_XXXXXX.png`
- `labels/train/synthetic_XXXXXX.json`
- `manifest.jsonl`

## 1) Ground-truth generation (`ground_truth_generator.py`)

For each target:

- Create **6 ends**.
- Each end contains **6 arrows**.
- Arrow value is sampled from:
  - `X, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, M`
- Score mapping:
  - `X` and `10` -> `10`
  - `M` -> `0`
  - others -> integer value
- For each end:
  - compute `subtotal` (sum of 6 arrows),
  - update `cumulative`.
- Track:
  - `x_count` (`X` only),
  - `x_plus_ten_count` (all score==10, including `X` and `10`),
  - `total` (final cumulative).

## 2) Rendering into template (`sheet_renderer.py`)

`SheetRenderer` draws generated values into detected table cells.

### 2.1 Detect table lines

From grayscale template image:

- A column is considered a dark vertical line candidate if enough pixels are dark.
- A row is considered a dark horizontal line candidate if enough pixels are dark.
- Nearby candidate indices are merged into one representative line.

### 2.2 Detect 4 athlete scoring regions

To prevent text from drifting outside tables:

- detect row bands with plausible large height for score areas,
- detect column bands with plausible width for each athlete block,
- pick/sort the resulting four major rectangular regions.

If exactly 4 regions cannot be found, renderer returns no cells and skips drawing values.

### 2.3 Build inner cells and draw text

For each of the 4 major regions:

- collect vertical/horizontal lines that fall inside the region,
- form inner cells from adjacent line pairs,
- filter by plausible row/column size,
- center text in each cell.

Flattened value order is:

- for each target,
- for each end:
  - 6 arrow values,
  - end subtotal,
  - end cumulative,
- then target summary:
  - `x_count`, `x_plus_ten_count`, `total`.

## 3) Label format (`models.py`)

Each image label stores a serialized `SyntheticSheet`:

- `image_id`
- `seed`
- `targets` (4 targets)
  - target metadata and per-end/per-arrow details.

This JSON is intended as the ground truth used by downstream OCR/parsing experiments.

## Notes and limitations

- Renderer currently depends on line-density heuristics; highly different templates may require threshold tuning.
- If line detection fails, image can be generated without injected numbers.
- Generation is deterministic for the same seed/template/code version.
