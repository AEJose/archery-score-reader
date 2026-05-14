# OCR Pipeline Accuracy Analysis

## Evaluation Summary

| Metric | Result |
|--------|--------|
| Dataset | 100 synthetic images, 4 targets each |
| Total arrows evaluated | 14,400 |
| Arrow exact match | 985 / 14,400 = **6.8%** |
| Arrow score-equivalent match (X=10) | 1,120 / 14,400 = **7.8%** |
| Target total exact match | 4 / 400 = **1.0%** |
| Incomplete targets (arrow count < 36) | 0 / 400 |

Accuracy is near-random. The pipeline successfully extracts enough tokens to fill all 4 targets, but the **values are almost entirely wrong**.

---

## Root Cause Analysis

### Problem 1: Token Order Mismatch (Critical)

The `ScoreSheetParser` uses **layout-agnostic sequential mapping**: it takes the first 144 valid score-like tokens and fills 4 targets x 36 arrows in order. However, the OCR token stream does not follow the logical arrow order.

**Evidence from raw token dump** (synthetic_000001.png, 244 tokens total):

The OCR returns tokens roughly top-to-bottom, left-to-right across the **entire page**. This means tokens from all 4 target columns are **interleaved by y-coordinate**, not grouped by target block.

Example: tokens at y~220-250 include values from target columns at x=300-400 (target 1), x=550-650 (target 2), x=800-900 (target 3) simultaneously:
```
[37] text=2  bbox=(348, 229, ...)   <- target 1 area
[40] text=X  bbox=(558, 225, ...)   <- target 2 area
[35] text=4  bbox=(810, 222, ...)   <- target 3 area
```

The parser assumes sequential token order = logical arrow order, but the actual order is a horizontal scan across all 4 targets simultaneously.

**Impact**: Even if every character is recognized correctly, the values get assigned to the wrong target/end/arrow positions.

### Problem 2: Non-Arrow Tokens Pollute the Stream (Critical)

The parser's `_normalize_token()` accepts any string that matches `{X, M, 10, 9, 8, ..., 1, 0}`. But the score sheet contains many non-arrow numeric values that also pass this filter:

| Token type | Examples from dump | Count per sheet |
|------------|-------------------|-----------------|
| Subtotals (per 3 arrows) | `29`, `27`, `33`, `46` | up to 48 (4 targets x 6 ends x 2 rows) |
| End scores | `46`, `35`, `39` | up to 24 |
| Cumulative scores | `46`, `81`, `120`, `158`, `193`, `223` | up to 24 |
| Target totals | `223`, `208`, `220`, `202` | 4 |
| X count / X+10 count | `6`, `14`, `5`, `9` | up to 8 |
| Header numbers (target no.) | `1`, `2`, `3`, `4` | varies |
| Multi-digit fragments | `17`, `13`, `16` | varies |

Many of these (single-digit subtotals like `6`, `8`, `1`) pass `_normalize_token()` and get treated as arrow scores. The raw dump shows **244 total tokens**, of which a significant portion are subtotals/cumulative values misidentified as arrows.

**Impact**: Non-arrow values shift all subsequent arrow assignments, compounding the ordering error.

### Problem 3: OCR Character-Level Errors (Minor, relative to above)

Some character-level recognition errors exist but are a minor contributor compared to Problems 1 and 2:

| Confusion | Examples from dump |
|-----------|-------------------|
| `X` recognized as `×` (Unicode multiply) | `[99] text=× conf=0.511`, `[137] text=× conf=0.504` |
| Trailing period `.` appended | `[21] text=7. conf=0.758`, `[38] text=3. conf=0.840` |
| Multi-char merge | `[123] text=6×6 conf=0.833`, `[153] text=6M conf=0.956` |
| Chinese label fragments pass through | `[113] text=Z conf=0.611` (misread of 之 or similar) |

Current `_normalize_token()` already handles `x`->`X` case-insensitively, but does **not** handle:
- Unicode `×` (U+00D7) as `X`
- Trailing punctuation stripping before validation
- Multi-character tokens that contain a valid score embedded in noise

---

## Current Pipeline Architecture

```
Image
  |
  v
OCREngine.run()                    # RapidOCR whole-page scan
  | returns: list[OCRToken]        # ~244 tokens with text + confidence + bbox
  |                                # ordered roughly top-to-bottom, left-to-right
  v                                # across ALL 4 target columns interleaved
ScoreSheetParser.parse()
  | step 1: _normalize_token()     # filter to valid score values
  | step 2: sequential slice       # values[0:36] -> target 1
  |                                # values[36:72] -> target 2
  |                                # values[72:108] -> target 3
  |                                # values[108:144] -> target 4
  v
StructuredScoreSheet               # result with wrong arrow assignments
```

### Key Code Locations

| Component | File | Lines |
|-----------|------|-------|
| OCR engine (RapidOCR wrapper) | `src/score_reader/recognition/ocr_engine.py` | 32-60 |
| Token normalization | `src/score_reader/processing/score_sheet_parser.py` | 10-19 |
| Sequential mapping | `src/score_reader/processing/score_sheet_parser.py` | 34-57 |
| Data models | `src/score_reader/recognition/models.py` | 1-41 |

---

## Synthetic Image Layout

Each synthetic image is ~1100x769px and contains:

```
+------------------------------------------------------------------+
| Header: 日期 / 賽事                                                |
+----------+-----------+-----------+-----------+
| Target 1 | Target 2  | Target 3  | Target 4  |
| x:44-291 | x:301-548 | x:559-805 | x:818-1064|
|          |           |           |           |
| 12 rows  | 12 rows   | 12 rows   | 12 rows   |  y: ~193-619
| (6 ends  | (6 ends   | (6 ends   | (6 ends   |
|  x2 rows)|  x2 rows) |  x2 rows) |  x2 rows) |
+----------+-----------+-----------+-----------+
| Footer: X count, X+10, Total, Signatures                         |
+------------------------------------------------------------------+
```

Per target block, each end occupies 2 rows:
```
Row A: [Arrow1] [Arrow2] [Arrow3] [Subtotal_top3] [EndScore] [Cumulative]
Row B: [Arrow4] [Arrow5] [Arrow6] [Subtotal_bot3] [        ] [          ]
```

Cell detection finds ~90 cells per target block (~360 total). The `SheetRenderer` knows exact cell positions and places values correctly during generation. But the **read-back pipeline does not use this geometry**.

---

## Recommended Fix: Geometry-Aware Cell Extraction

### Strategy

Replace the current whole-page token stream with a **cell-by-cell OCR** approach:

1. **Detect target regions** — Use contour detection or template matching to find the 4 target blocks (already implemented in `SheetRenderer._detect_target_regions()`).

2. **Detect grid cells within each region** — Use line detection to find row/column boundaries (already implemented in `SheetRenderer._detect_region_grid_lines()` and `_detect_cells_for_orientation()`).

3. **Classify each cell by position** — Based on column index within the grid:
   - Columns 0-2: arrow values (top row = arrows 1-3, bottom row = arrows 4-6)
   - Column 3: subtotal
   - Column 4: end score (top row only)
   - Column 5: cumulative (top row only)

4. **Run OCR per-cell** — Crop each arrow cell and run RapidOCR on the crop. This eliminates:
   - Token ordering issues (position is known from the grid)
   - Non-arrow value pollution (only arrow cells are processed)
   - Multi-token merging issues (one cell = one value)

5. **Map cell values to logical structure** — Using known grid position:
   ```
   target_index = region_index (0-3)
   end_index = row_pair_index (0-5)
   arrow_index = col_index + (3 if bottom_row else 0)
   ```

### Existing Code to Reuse

The `SheetRenderer` already contains the detection logic needed for reading:

| Function | Location | Can be reused for |
|----------|----------|-------------------|
| `_detect_target_regions()` | `sheet_renderer.py:261-289` | Finding 4 target blocks |
| `_detect_region_grid_lines()` | `sheet_renderer.py:141-176` | Finding row/column boundaries |
| `_detect_cells_for_orientation()` | `sheet_renderer.py:79-105` | Creating cell rectangles |
| `_group_cells_by_rows()` | `sheet_renderer.py:241-259` | Organizing cells into rows |

These functions currently live in the dataset generation module but perform **generic image analysis** that applies equally to reading score sheets.

### Additional Improvements

- **Normalize Unicode**: Add `×` (U+00D7) -> `X` mapping in `_normalize_token()`.
- **Strip punctuation**: Remove trailing `.` before validation.
- **Handle merged text**: If a cell OCR result contains multiple characters like `6M`, split and take the primary value.
- **Confidence-based filtering**: Use per-cell confidence to flag uncertain readings for human review.

---

## Evaluation Script

The evaluation was run with this command:

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && uv run python3 /tmp/eval_ocr.py"
```

The script compares OCR output against ground truth labels in `dataset/generated/labels/train/` for all 100 synthetic images. It reports:
- Per-arrow exact match (value string equality)
- Per-arrow score-equivalent match (X and 10 both count as 10)
- Per-target total match
- Sample error listing (first 50 mismatches)

---

## Priority

| Priority | Task | Expected Impact |
|----------|------|-----------------|
| P0 | Implement geometry-aware cell extraction | Fixes token ordering + non-arrow pollution. Should raise accuracy from ~7% to a usable baseline. |
| P1 | Normalize Unicode and punctuation in `_normalize_token()` | Fixes ~5-10% of character-level errors. |
| P2 | Add per-cell confidence tracking and review item export | Enables human-in-the-loop verification for uncertain cells. |
| P1.5 | Add debug visualization overlay | Enables human review of each pipeline step on the original image. |
| P3 | Add orientation correction before OCR | Handles rotated/flipped images in real-world data. |

---

## Feature Request: Debug Visualization Overlay

### Goal

產生 debug overlay 圖片，在原圖上逐步疊加每個處理階段的結果，讓人類可以直觀 review pipeline 的行為是否正確。

### Output

給定一張計分表圖片，產出以下 4 張 debug 圖片到指定目錄：

| File | Content |
|------|---------|
| `step1_target_regions.png` | 原圖 + 4 個選手紀錄區域外框 |
| `step2_cells.png` | 原圖 + 區域外框 + 每個偵測到的 cell 邊框 |
| `step3_ocr_results.png` | 原圖 + 區域外框 + cell 邊框 + 每個 OCR token 的辨識文字與信心度 |
| `combined.png` | 同 step3（完整疊加，方便單張快速 review） |

### Step 1: Target Region Detection Overlay

- 使用 `SheetRenderer._detect_target_regions()` 偵測 4 個選手區塊
- 每個區塊用不同顏色的矩形框標示（建議：紅/綠/藍/黃，線寬 2-3px）
- 在框的左上角標示 `Target 1` ~ `Target 4`

```
+--[ Target 1 (red) ]--+--[ Target 2 (green) ]--+--[ Target 3 (blue) ]--+--[ Target 4 (yellow) ]--+
|                       |                        |                       |                         |
|                       |                        |                       |                         |
+-----------------------+------------------------+-----------------------+-------------------------+
```

### Step 2: Cell Detection Overlay

- 在 step1 的基礎上，使用 `SheetRenderer._detect_cells_for_orientation()` 偵測每個 cell
- 每個 cell 畫半透明邊框（淺灰色，線寬 1px）
- 目標是看到完整的 grid 結構是否正確對齊到原始表格

### Step 3: OCR Results Overlay

- 在 step2 的基礎上，執行 `OCREngine.run()` 取得所有 OCR token
- 在每個 token 的 bbox 位置疊加一個小標籤，顯示：
  - 辨識出的文字
  - 信心度百分比（如 `X 95%`）
- 標籤顏色依信心度區分：
  - `confidence >= 0.8`：綠色背景
  - `0.5 <= confidence < 0.8`：黃色背景
  - `confidence < 0.5`：紅色背景
- 文字用黑色，背景半透明

### CLI Interface

新增一個 CLI 子命令：

```bash
score-reader debug-visualize --image <image_path> --output <output_dir>
```

### Implementation Notes

#### 可重用的現有函式

| Function | Location | 用途 |
|----------|----------|------|
| `_detect_target_regions()` | `src/score_reader/dataset/generator/sheet_renderer.py` | 偵測 4 個 target 區域 |
| `_detect_cells_for_orientation()` | 同上 | 偵測格子 |
| `_detect_region_grid_lines()` | 同上 | 偵測格線 |
| `_group_cells_by_rows()` | 同上 | 將 cell 按行分組 |
| `OCREngine.run()` | `src/score_reader/recognition/ocr_engine.py` | 取得 OCR token + bbox |

這些偵測函式目前是 `SheetRenderer` 的 method，實作時可以：
- 抽成獨立的 utility function（放在 `src/score_reader/image/` 或 `src/score_reader/extraction/`），讓 renderer 和 visualizer 都能用
- 或直接實例化 `SheetRenderer` 呼叫（但語意上不太對，renderer 是用來產生資料的）

建議選擇前者（抽成 utility），以利後續 geometry-aware parser 也能重用。

#### 繪圖技術

- 使用 OpenCV（`cv2.rectangle`, `cv2.putText`, `cv2.addWeighted`）
- 中文字型如果需要用 Pillow 的 `ImageFont` + `ImageDraw`（OpenCV 的 `putText` 不支援中文）
- 標籤不需要中文，只需英文/數字（`Target 1`, `X 95%`），所以 OpenCV 即可

#### 新增檔案

```
src/score_reader/visualization/
    __init__.py
    overlay.py          # 核心繪圖邏輯
```

#### 修改檔案

```
src/score_reader/cli.py   # 新增 debug-visualize 子命令
```

### Verification

```bash
# 對合成資料跑
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && \
  uv run python -m score_reader.cli debug-visualize \
    --image dataset/generated/images/train/synthetic_000001.png \
    --output /tmp/debug_vis"

# 對真實資料跑
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && \
  uv run python -m score_reader.cli debug-visualize \
    --image tests/fixtures/real.png \
    --output /tmp/debug_vis_real"

# 確認輸出
ls /tmp/debug_vis/
# 預期：step1_target_regions.png  step2_cells.png  step3_ocr_results.png  combined.png
```

人工確認：
1. step1 的 4 個框是否正確框住 4 個選手區塊
2. step2 的 cell 邊框是否對齊原始表格格線
3. step3 的文字標籤位置是否落在對應的格子上，信心度顏色是否合理
