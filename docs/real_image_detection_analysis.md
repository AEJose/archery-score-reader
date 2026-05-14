# 真實影像偵測分析報告

> 基於 `real.png` 的實測結果，分析現有 pipeline 的缺口與後續實作方向。
> 本文件供後續 agent 作為實作依據。

---

## 1. 測試對象

| 項目 | 值 |
|------|-----|
| 影像檔案 | `tests/fixtures/real.png` |
| 尺寸 | 1100 × 769 px |
| 方向 | landscape（橫向拍攝） |
| 記分區數量 | **3 個**（左、中、右各一位選手） |
| 內容 | 手寫數字填入的射箭記分紙 |

### 與 sample.png（模板）的差異

| | sample.png（模板） | real.png（實拍） |
|--|-------------------|-----------------|
| 方向 | portrait 1200×1800 | landscape 1100×769 |
| 記分區 | 4 個（固定） | 3 個（第 4 區空白或不存在） |
| 內容 | 空白格線 | 手寫數字 |
| 歪斜 | 0° | **-6.07°** |
| 陰影 | 無 | 輕微（3%） |
| 透視變形 | 無 | 有（手持拍攝） |

---

## 2. 影像品質分析結果

使用 `image_quality.analyze_image_quality()` 取得：

```json
{
  "image_path": "real.png",
  "width": 1100,
  "height": 769,
  "estimated_skew_deg": -6.072,
  "orientation": "landscape",
  "shadow_ratio": 0.0298,
  "blur_score": 3286.481
}
```

| 指標 | 值 | 判定 |
|------|-----|------|
| 歪斜角度 | -6.07° | 接近但未超過 8° 拒絕門檻，需校正 |
| 陰影比率 | 2.98% | 良好（門檻 25%） |
| 模糊分數 | 3286.5 | 清晰（Laplacian variance 越高越清楚） |

---

## 3. 區域偵測結果

使用 `SheetRenderer._detect_target_regions()` 偵測：

**偵測到 4 個區域，但其中 1 個是誤判。**

| 區域 | 座標 (x1,y1)→(x2,y2) | 尺寸 | 實際內容 | 判定 |
|------|----------------------|------|----------|------|
| 0 | (32,235)→(316,668) | 284×433 | 左側記分區 | 正確 |
| 1 | (262,38)→(754,147) | 492×109 | **表頭區域** | **誤判** |
| 2 | (279,208)→(564,642) | 285×434 | 中間記分區 | 正確 |
| 3 | (526,181)→(813,615) | 287×434 | 右側記分區 | 正確 |

debug 視覺化輸出：`tests/fixtures/debug_output/real_debug_regions.png`

### 誤判原因

- `_detect_target_regions` 篩選面積在 `total_area / 8 ± 50%` 的輪廓
- 表頭的 bounding box（492×109 = 53,628）恰好落入面積門檻範圍
- 程式硬編碼取前 4 個區域（`regions[:4]`），導致表頭被選入

---

## 4. 格子偵測結果

使用 `SheetRenderer._detect_cells()` 偵測：

**回傳 0 組格子 — 完全失敗。**

### 失敗根因

1. **全域格線掃描策略不適用真實影像**
   - `_detect_cells` 逐列/逐行掃描整張影像，找「暗像素佔比 > 20%」的行列
   - 真實照片有 -6° 歪斜，格線不再精確落在同一 x 或 y 座標
   - 全域暗像素比例被稀釋，找不到足夠的水平/垂直格線

2. **硬編碼要求剛好 4 個 region**
   - `if len(regions) != 4: return []`
   - 真實影像只有 3 個記分區，即使區域偵測修正後仍會因數量不符而 early return

3. **閾值為合成模板設計**
   - dark pixel threshold `< 130`、ratio `> 20%` 適用於乾淨的黑白模板
   - 真實照片的格線對比度較低，無法通過同樣的閾值

---

## 5. 現有元件能力盤點

| 元件 | 檔案 | 對真實影像的可用性 |
|------|------|-------------------|
| 影像品質分析 | `src/score_reader/dataset/image_quality.py` | **可用** — 能正確分析歪斜、模糊、陰影 |
| 區域偵測 | `sheet_renderer._detect_target_regions()` | **部分可用** — 能找到區域但會誤判表頭 |
| 格子偵測 | `sheet_renderer._detect_cells()` | **不可用** — 全域掃描策略對真實影像失效 |
| 文字辨識 (OCR) | 不存在 | **未實作** — 無任何 OCR 引擎 |
| Baseline 偵測器 | `evaluation.BaselineDetector` | **不適用** — 輸入是 JSON 不是影像 |
| 評估框架 | `evaluation.evaluate_dataset()` | **可沿用** — 只要 prediction 格式符合 schema |

---

## 6. 記分紙結構分析（來自模板 + 實拍觀察）

### 6.1 表頭區

- 日期、賽事名稱
- 每位選手：單位、姓名、靶位

### 6.2 記分區（每位選手一個）

每個記分區的欄位配置：

```
列標題: | 1 | 2 | 3 | 小計 | 得分 | 累計 |
```

- 行 1–6：每行代表一個 end（輪）
- 每個 end 佔 **2 列**：
  - 上列：箭 1–3 + 上半小計
  - 下列：箭 4–6 + 下半小計
- 右側兩欄「得分」「累計」跨兩列合併

### 6.3 底部統計

- X 次數
- X+10 次數
- 總計
- 選手簽名

### 6.4 Output Schema（已定義）

```json
{
  "image_id": "string",
  "targets": [
    {
      "target_index": 0,
      "target_no": "1A",
      "rounds": [
        {
          "end": 1,
          "arrows": [
            { "arrow": 1, "value": "10", "score_value": 10 }
          ],
          "subtotal": 46,
          "cumulative": 46
        }
      ],
      "total": 223,
      "x_count": 6,
      "x_plus_ten_count": 14
    }
  ]
}
```

完整定義見：`src/score_reader/dataset/models.py`

箭值類別：`X, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, M`（共 12 類）

---

## 7. 需要實作的完整 Pipeline

```
tests/fixtures/real.png
  │
  ▼
[Step 1] 影像前處理 (preprocessing)
  │  - 歪斜校正 (deskew)
  │  - 透視校正 (perspective correction)
  │  - 二值化 / 對比增強
  ▼
[Step 2] 記分區偵測 (region detection)
  │  - 偵測 N 個記分區（不硬編碼 4）
  │  - 過濾表頭等非記分區域
  │  - 輸出每個記分區的 bounding box
  ▼
[Step 3] 格子偵測 (cell detection)
  │  - 對每個記分區獨立做格線偵測（非全域）
  │  - 使用 Hough lines 或 morphological 方法
  │  - 容忍傾斜與不完美格線
  │  - 輸出每個 cell 的座標
  ▼
[Step 4] 格子分類 (cell classification)
  │  - 識別哪些 cell 是箭值、小計、得分、累計
  │  - 基於位置規則（行列相對位置）
  ▼
[Step 5] 文字辨識 (OCR)
  │  - 對每個箭值 cell 做字元辨識
  │  - 辨識類別：X, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, M
  │  - 可選方案：Tesseract / PaddleOCR / 自訓練 CNN
  ▼
[Step 6] 結構化組裝 (assembly)
  │  - 將辨識結果組裝成 SyntheticSheet schema
  │  - 計算 subtotal, cumulative, total, x_count 等
  │  - 可用辨識到的小計/累計做交叉驗證
  ▼
[Step 7] 評估 (evaluation)
     - 直接沿用現有 evaluate_dataset()
     - 比對 prediction vs ground truth
```

---

## 8. 各步驟技術細節與建議

### Step 1：影像前處理

**位置建議**：`src/score_reader/detection/preprocessing.py`

```python
def preprocess(image_path: Path) -> np.ndarray:
    """讀取影像 → 歪斜校正 → 透視校正 → 回傳校正後灰階影像。"""
```

- 歪斜校正：已有 `image_quality._estimate_skew_angle()` 可算角度，用 `cv2.getRotationMatrix2D` + `cv2.warpAffine` 做旋轉
- 透視校正：偵測記分紙的四個角點，用 `cv2.getPerspectiveTransform` 拉正
- 二值化：`cv2.adaptiveThreshold` 比固定閾值更能適應不同光線

### Step 2：記分區偵測

**位置建議**：`src/score_reader/detection/region_detector.py`

需改進項目：

| 現有問題 | 建議修改 |
|---------|---------|
| 硬編碼 4 個區域 | 改為動態偵測 N 個（N ≥ 1） |
| 表頭誤判 | 加入長寬比過濾：記分區應為近正方形或縱向長方形，表頭為扁平橫向 |
| 面積閾值不適用 | 改為相對面積 + 長寬比雙重過濾 |

過濾規則建議：
```python
aspect_ratio = rh / rw
# 記分區: aspect_ratio > 1.0（高 > 寬）
# 表頭:   aspect_ratio < 0.5（寬 >> 高）→ 排除
```

### Step 3：格子偵測

**位置建議**：`src/score_reader/detection/cell_detector.py`

核心改動：**對每個記分區獨立做格線偵測**（非全域掃描）。

建議方法：
1. 裁切出記分區子影像
2. 用 `cv2.HoughLinesP` 偵測水平與垂直線段
3. 將線段聚類為格線（clustering by angle + intercept）
4. 交叉點即為格子頂點

或者用 morphological approach：
```python
# 水平線 kernel
h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
# 垂直線 kernel
v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
```

### Step 4：格子分類

**位置建議**：可整合在 cell_detector 或獨立為 `cell_classifier.py`

每個記分區的格子配置已知（來自模板）：
- 6 欄：`[箭1, 箭2, 箭3, 小計, 得分, 累計]`
- 12 行（6 ends × 2 列/end）
- 底部 3 行：X count、X+10 count、總計

分類可用**位置規則**（不需 ML）：按行列排序後根據相對位置指定語義。

### Step 5：文字辨識 (OCR)

**位置建議**：`src/score_reader/detection/ocr.py`

選項比較：

| 方案 | 優點 | 缺點 |
|------|------|------|
| Tesseract (pytesseract) | 成熟、無需訓練 | 對手寫辨識較弱，需要 fine-tune |
| PaddleOCR | 手寫辨識能力較強 | 套件較重 |
| 自訓練 CNN/分類器 | 最適合本場景（12 類固定） | 需要標註資料（但已有合成資料 pipeline） |
| Template matching | 最簡單 | 手寫體變異大，效果有限 |

**建議初版用 Tesseract**，後續用合成資料訓練專用分類器。

辨識後需要後處理：
```python
VALID_VALUES = {"X", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "M"}

def postprocess_ocr(raw: str) -> str:
    """將 OCR 原始輸出映射到有效箭值。"""
    raw = raw.strip().upper()
    if raw in VALID_VALUES:
        return raw
    # 常見混淆處理：0→10? O→0? l→1?
    ...
```

### Step 6：結構化組裝

**位置建議**：`src/score_reader/detection/assembler.py`

```python
def assemble_sheet(
    regions: list[RegionResult],
    cells_per_region: list[list[CellResult]],
    ocr_results: list[list[str]],
) -> dict:
    """組裝成與 SyntheticSheet.to_dict() 相同格式的 dict。"""
```

交叉驗證邏輯：
- 計算箭值加總是否等於辨識到的小計
- 計算累計是否正確遞增
- 不一致時標記 `confidence: low`

### Step 7：CLI 入口

在 `cli.py` 新增命令：

```python
@app.command("detect")
def detect(
    image: Path = typer.Argument(..., exists=True),
    output: Path = typer.Option("./detection_result.json"),
) -> None:
    """對真實影像執行記分偵測。"""
```

---

## 9. 新增依賴

```toml
# pyproject.toml
dependencies = [
    # ... 既有 ...
    "pytesseract>=0.3",    # OCR (若選 Tesseract)
]
```

系統需安裝 Tesseract：
```bash
sudo apt-get install tesseract-ocr
```

---

## 10. 檔案結構建議

```
src/score_reader/
├── detection/                    # 新增：真實影像偵測模組
│   ├── __init__.py
│   ├── preprocessing.py          # Step 1: 歪斜/透視校正
│   ├── region_detector.py        # Step 2: 記分區偵測
│   ├── cell_detector.py          # Step 3: 格子偵測
│   ├── ocr.py                    # Step 5: 文字辨識
│   └── assembler.py              # Step 6: 結構化組裝
├── dataset/                      # 既有：合成資料 pipeline
│   ├── evaluation.py             # 可沿用
│   ├── models.py                 # 可沿用（output schema）
│   └── ...
└── cli.py                        # 新增 detect 命令
```

---

## 11. 測試策略

### 11.1 用合成資料做 regression test

已有 100 張合成影像 + ground truth，可以：
1. 對合成影像跑完整 pipeline（不加 artifact）→ 預期 accuracy ~100%
2. 對合成影像加 artifact 後跑 pipeline → 衡量 preprocessing 的校正效果

### 11.2 用 tests/fixtures/real.png 做 integration test

1. 手動標註 `tests/fixtures/real.png` 的 ground truth（JSON 格式同 `models.py`）
2. 跑 pipeline 後用 `evaluate_dataset()` 比對
3. 逐步排查哪個 step 損失最大

### 11.3 建議優先順序

1. **先跑通 Step 1–3**（preprocessing → region → cell），輸出 debug 視覺化確認格子偵測正確
2. **再接 Step 5 OCR**，用最簡單的 Tesseract 先出 baseline 數字
3. **最後做 Step 6 組裝 + Step 7 評估**，接上既有 evaluate 框架

---

## 12. 風險與注意事項

| 風險 | 影響 | 緩解方式 |
|------|------|---------|
| 記分區數量不固定（3 或 4） | pipeline 會因硬編碼而失敗 | 改為動態偵測 N 個 |
| 手寫體變異大 | OCR 準確率低 | 先用合成資料訓練，再用真實資料 fine-tune |
| 不同記分紙格式 | 欄位配置不同 | 先只支援 sample.png 這種格式，後續擴充 |
| 拍攝角度/光線差異大 | preprocessing 不穩定 | 設品質閘門，不合格的退回重拍 |
| WSL + Windows 環境權限問題 | `uv run pytest` 需用 `python -m pytest` | 已知 workaround |

---

## 13. 快速驗證命令（供實作完成後使用）

```bash
# 對 real.png 跑偵測
uv run score-reader detect tests/fixtures/real.png --output ./real_result.json

# 如果有 ground truth，跑評估
MANIFEST=./real_manifest.jsonl \
OUTPUT_DIR=./real_eval \
DETECT_MODE=model \
bash scripts/run_detection_workflow.sh
```
