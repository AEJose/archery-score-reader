# Pipeline V2：基於幾何定位的計分表辨識

## 現況問題

目前的 pipeline（`ScoreSheetParser.parse()`）對整頁做 OCR，然後把前 144 個看起來像分數的 token 盲切成 4 靶位 x 36 箭。準確率只有 **6.8%**，原因：

1. **沒有影像校正** — 手持拍攝的透視/旋轉變形完全沒處理。
2. **沒有區域隔離** — OCR 掃整頁，把表頭、小計、累計、簽名欄的數字全部混進來。
3. **沒有空間對位** — token 按掃描順序分配到靶位/箭，不是按格子位置。

## 新 Pipeline

```
Step 0: 載入圖片
Step 1: 影像校正（方向偵測 + 去歪斜 + 透視校正）
Step 2: 選手區域偵測（找出 4 個選手記錄區塊）
Step 3: 逐區域格線偵測（grid lines -> cells）
Step 4: Cell 分類（哪些是箭支、哪些是小計/累計/表頭）
Step 5: 逐格 OCR（只裁切箭支格子，逐格辨識）
Step 6: 結構組裝（依格子座標組裝成 target/end/arrow）
Step 7: 交叉驗證（用小計/累計反推檢查）
```

每一步都產出中間結果，每一步都輸出 debug 圖片供視覺化檢查。

---

## Step 0：載入圖片

**輸入**：圖片路徑（PNG/JPG）
**輸出**：BGR numpy array

直接 `cv2.imread()`。

---

## Step 1：影像校正

**輸入**：原始 BGR 圖片
**輸出**：校正後的灰階圖片（已去歪斜、透視校正）

### 1a. 方向偵測

偵測圖片是否被旋轉了 90/180/270 度。

策略：嘗試 4 個旋轉方向（0, 90, 180, 270），對每個方向跑 target region detection，選出偵測結果最好的那個方向（找到最多區域、或符合預期的橫向版面比例）。

現有程式碼：`SheetRenderer._detect_cells()` 已經有這個迴圈，位於 [sheet_renderer.py:61-77](src/score_reader/dataset/generator/sheet_renderer.py#L61-L77)。

### 1b. 去歪斜（Deskew）

校正小角度旋轉（手持傾斜，通常 -10 到 +10 度）。

現有程式碼：`SheetRenderer._deskew()` 位於 [sheet_renderer.py:178-206](src/score_reader/dataset/generator/sheet_renderer.py#L178-L206)，用 Hough 直線偵測找中位角度，然後做仿射旋轉。

### 1c. 透視校正（新功能）

偵測計分表的四邊形邊界，warp 成矩形，修正手持拍攝的梯形變形。

策略：
1. 邊緣偵測 + 輪廓尋找，找到最大的矩形輪廓（整張計分表的外框）。
2. 排序 4 個角點（左上、右上、右下、左下）。
3. 用 `cv2.getPerspectiveTransform()` + `cv2.warpPerspective()` warp 成目標矩形。

如果找不到明確的四邊形，跳過此步（圖片可能已經是平的）。

### Debug 輸出

`step1_corrected.png` — 校正後的圖片，疊加顯示所做的變換。

---

## Step 2：選手區域偵測

**輸入**：校正後的灰階圖片
**輸出**：4 個區域的 bounding box `[(left, top, right, bottom), ...]`

偵測 4 個選手計分區塊。

現有程式碼：`SheetRenderer._detect_target_regions()` 位於 [sheet_renderer.py:261-289](src/score_reader/dataset/generator/sheet_renderer.py#L261-L289)。

目前的參數：
- 面積過濾：佔整張圖的 4%-24%
- 長寬比：高 > 1.1 倍寬
- 填充率：> 45%

這些參數在乾淨模板和加了 artifacts 的合成圖上都能正常偵測到 4 個區域（已驗證）。

按 x 座標排序（左到右），取前 4 個。

### Debug 輸出

`step2_target_regions.png` — 校正後的圖片上畫 4 個彩色矩形框。

---

## Step 3：逐區域格線偵測

**輸入**：校正後的灰階圖片 + 4 個區域 bounding box
**輸出**：每個區域的 `Cell(left, top, right, bottom)` 列表，按行分組

**這是目前在加了 artifacts 的圖片上會失敗的步驟。** 現有的 `_detect_region_grid_lines()` 回傳 0 條線，因為閾值是針對乾淨模板調的。

### 失敗原因

現有實作位於 [sheet_renderer.py:141-176](src/score_reader/dataset/generator/sheet_renderer.py#L141-L176)，使用：
- `cv2.adaptiveThreshold` 搭配 `blockSize=21, C=7`
- 形態學 open，核心尺寸嚴格
- 投影閾值：垂直線需 >18% 欄高，水平線需 >22% 列寬

在有噪點、陰影、透視殘留的圖片上，這些閾值太嚴格。

### 建議修正

建立一個更強健的格線偵測版本：

1. **前處理**：先做 CLAHE（對比度限制自適應直方圖均衡化）來標準化光線/陰影，再做二值化。
2. **多閾值嘗試**：嘗試多組 `adaptiveThreshold` 參數（不同 `blockSize` 和 `C`），合併結果。
3. **降低投影閾值**：從 18%/22% 降到 ~12%/15%，因為實際圖片的格線可能斷裂。
4. **線段合併**：如果形態學方法找到太少線，改用 Hough 直線偵測作為 fallback。
5. **幾何驗證**：偵測後驗證 grid 是否合理（行高大致相等、欄寬大致相等），剔除離群線。

### 預期的格子結構（每個 target）

```
欄：7 條垂直線 -> 6 欄
  [箭1] [箭2] [箭3] [3箭小計] [該輪得分] [累計]

行：13-17 條水平線 -> 12-16 行
  第 0 行（表頭）：單位 / 姓名 / 靶位號
  第 1-2 行：第 1 輪（上半 3 箭、下半 3 箭）
  第 3-4 行：第 2 輪
  ...
  第 11-12 行：第 6 輪
  第 13+ 行：底部（X 數、總分、簽名）
```

### Cell 輸出格式

每個區域產出按行分組的 cell 列表：
```python
[
  [Cell, Cell, Cell, Cell, Cell, Cell],  # 第 0 行
  [Cell, Cell, Cell, Cell, Cell, Cell],  # 第 1 行
  ...
]
```

### Debug 輸出

`step3_cells.png` — 校正後的圖片上畫區域框 + 所有偵測到的 cell 邊框。

---

## Step 4：Cell 分類

**輸入**：每個區域按行分組的 cells
**輸出**：每個區域的 cell 映射 `{ (end_idx, arrow_idx): Cell, (end_idx, "subtotal_top"): Cell, ... }`

純粹依據 **格子位置**（不需要 OCR）來分類每個 cell：

```
計分行 = rows[表頭偏移量 : 表頭偏移量 + 12]（跳過表頭）

每一輪 (0-5)：
  row_a = scoring_rows[輪次 * 2]      # 該輪上半行
  row_b = scoring_rows[輪次 * 2 + 1]  # 該輪下半行

  row_a[0] = 箭 1    row_a[1] = 箭 2    row_a[2] = 箭 3
  row_a[3] = 上半小計
  row_a[4] = 該輪得分
  row_a[5] = 累計

  row_b[0] = 箭 4    row_b[1] = 箭 5    row_b[2] = 箭 6
  row_b[3] = 下半小計
```

這和 `_build_target_placement()` 位於 [sheet_renderer.py:208-237](src/score_reader/dataset/generator/sheet_renderer.py#L208-L237) 的邏輯完全相同，只是方向相反（讀取而非寫入）。

表頭偏移量的偵測策略：找到第一對行高與資料行一致的行（表頭行通常比較高或有合併儲存格）。

### 輸出格式

```python
@dataclass
class CellMap:
    arrow_cells: list[tuple[int, int, Cell]]       # (輪次, 箭序, cell)
    subtotal_cells: list[tuple[int, str, Cell]]     # (輪次, "top"/"bottom", cell)
    end_score_cells: list[tuple[int, Cell]]         # (輪次, cell)
    cumulative_cells: list[tuple[int, Cell]]        # (輪次, cell)
```

---

## Step 5：逐格 OCR

**輸入**：校正後的圖片（BGR）+ 分類好的箭支 cells
**輸出**：每格的辨識值 + 信心度

對每個箭支 cell：
1. 從**校正後的圖片**裁切該格區域（加 ~2-3px padding）。
2. 對裁切圖執行 OCR。
3. 用 `_normalize_token()` 正規化結果。

**只有箭支格子（第 0-2 欄）送去 OCR。** 小計、得分、累計可以選擇性 OCR 作為驗證用途，但不作為主要輸出。

### OCR 引擎

繼續使用 `RapidOCR`。對小格裁切圖，效果應比整頁掃描更好，因為：
- 沒有其他區域的文字干擾
- 聚焦的上下文 = 更高準確率
- 一格 = 一個值（不會有多 token 分割問題）

### 正規化改進

更新 `_normalize_token()` 以額外處理：
- Unicode `×`（U+00D7）-> `X`
- 去除尾端標點（`.`、`,`）
- 多字元結果：如果 OCR 回傳 `6M` 或 `10.`，擷取主要值

### 輸出格式

```python
@dataclass
class CellReading:
    end_index: int
    arrow_index: int    # 1-6
    cell: Cell
    raw_text: str
    value: str          # 正規化後：X, 10, 9, ..., 1, M
    confidence: float
```

### Debug 輸出

`step5_ocr_results.png` — 校正後的圖片上標示箭支格子，疊加 OCR 文字標籤。

---

## Step 6：結構組裝

**輸入**：4 靶位 x cell readings
**輸出**：`StructuredScoreSheet`（和目前相同的 model）

把辨識結果組裝成既有的資料結構：

```python
for 每個靶位 (0-3):
    for 每一輪 (0-5):
        arrows[0-5] = Step 5 的 cell readings
        subtotal = 箭支分數加總
    total = 所有 subtotal 加總
```

不猜測、不盲切。每個值的位置都由格子座標決定。

---

## Step 7：交叉驗證（選配，供 review 用）

**輸入**：組裝好的 `StructuredScoreSheet` + Step 5 的小計/累計 cell readings
**輸出**：驗證錯誤列表

用計算值和 OCR 辨識的小計/累計做交叉比對：
- `sum(箭 1-3)` 應等於 OCR 辨識的上半小計
- `sum(箭 4-6)` 應等於 OCR 辨識的下半小計
- `上半小計 + 下半小計` 應等於 OCR 辨識的該輪得分
- 逐輪累計應等於 OCR 辨識的累計欄

不一致代表特定格子可能有 OCR 錯誤 -> 標記為待人工複查。

---

## 檔案結構

### 新增檔案

```
src/score_reader/processing/
    image_corrector.py       # Step 1：去歪斜 + 透視校正
    region_detector.py       # Step 2：選手區域偵測（從 SheetRenderer 抽出）
    grid_detector.py         # Step 3：強健版格線 + cell 偵測
    cell_classifier.py       # Step 4：依格子位置分類 cell
    cell_ocr.py              # Step 5：逐格 OCR
    structure_assembler.py   # Step 6：組裝成 StructuredScoreSheet
    validator.py             # Step 7：交叉驗證
```

### 修改檔案

```
src/score_reader/processing/score_sheet_parser.py
    # 把目前的 parse() 替換成新 pipeline，依序呼叫 Step 1-6

src/score_reader/processing/__init__.py
    # Export 新的 class

src/score_reader/visualization/overlay.py
    # 更新 debug-visualize，顯示新 pipeline 每一步的結果

src/score_reader/cli.py
    # read-score-sheet 使用新 pipeline
    # debug-visualize 顯示所有步驟
```

### 從 SheetRenderer 抽出的程式碼

以下應從 `SheetRenderer` 搬到新模組，讓資料產生器和辨識 pipeline 都能共用：

| 目前位置 | 搬到 | 函式 |
|---------|------|------|
| `SheetRenderer._deskew()` | `image_corrector.py` | `deskew(gray) -> gray` |
| `SheetRenderer._detect_target_regions()` | `region_detector.py` | `detect_target_regions(gray) -> regions` |
| `SheetRenderer._dedupe_regions()` | `region_detector.py` | `dedupe_regions(regions) -> regions` |
| `SheetRenderer._detect_region_grid_lines()` | `grid_detector.py` | `detect_grid_lines(gray, region) -> (v_lines, h_lines)` |
| `SheetRenderer._merge_lines()` | `grid_detector.py` | `merge_lines(indices) -> merged` |
| `SheetRenderer._group_cells_by_rows()` | `grid_detector.py` | `group_cells_by_rows(cells) -> rows` |
| `Cell` dataclass | `src/score_reader/recognition/models.py` | 共用的 cell model |

抽出後，`SheetRenderer` 應 import 並委派給這些新模組（不能破壞現有的資料產生 pipeline）。

---

## 評估

實作完成後，重新跑 100 張合成圖的評估：

```bash
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && uv run python3 /tmp/eval_ocr.py"
```

預期改善：箭支準確率從 **6.8%** 提升到 **>60%**（剩餘錯誤來自 OCR 字元辨識，不再是結構錯位）。

## 開發與執行指令

```bash
# 安裝依賴
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && uv sync"

# 對單張圖片執行辨識
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && \
  uv run python -m score_reader.cli read-score-sheet \
    --image tests/fixtures/fake_data_sample2.png \
    --output /tmp/result.json"

# Debug 視覺化
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && \
  uv run python -m score_reader.cli debug-visualize \
    --image tests/fixtures/fake_data_sample2.png \
    --output /tmp/debug_vis"

# 執行測試
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && \
  uv run python -m pytest tests/ -v"

# 對 100 張合成圖做評估
wsl -d Ubuntu-22.04 bash -lc "cd /home/joseph/archery-score-reader && \
  uv run python3 /tmp/eval_ocr.py"
```

## 重要注意事項

- WSL 指令必須用 `bash -lc`（login shell，確保 uv 在 PATH 中）。
- 用 `python -m pytest` 而非直接跑 `pytest`（WSL 掛載的 .venv/bin 沒有執行權限）。
- 用 `python -m score_reader.cli` 而非 `score-reader` entry point。
- 所有程式碼在 `src/score_reader/`，以 `pyproject.toml` 定義的 package layout。
- **不要修改 `SheetRenderer.render()` 的行為** — 資料產生 pipeline 必須維持正常運作。
