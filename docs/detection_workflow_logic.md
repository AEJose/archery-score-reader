# 偵測與評估流程說明（Synthetic Data Workflow）

本文說明目前 `run_detection_workflow.sh` + `evaluation.py` 的**偵測邏輯**與**準確率計算方式**，以及未來如何替換成真實資料/真實模型。

---

## 1. 整體流程

入口腳本：`scripts/run_detection_workflow.sh`

流程分成三步：

1. **準備資料**
   - 若未提供 `MANIFEST` 環境變數：先呼叫既有 CLI 產生假資料
     - `uv run score-reader generate-dataset ...`
   - 若有提供 `MANIFEST`：直接重用既有資料集（不重生）

2. **執行偵測 + 比對評估**
   - 透過 `BaselineDetector` 對每張標註資料做 prediction
   - 用 `evaluate_dataset()` 將 prediction 與 ground truth 逐欄位比對

3. **輸出結果**
   - 產生 `detection_eval.json`
   - 內容包含整體 summary 與每張影像的 per-sheet accuracy

---

## 2. 目前「偵測邏輯」是什麼？

目前版本屬於**基準/模擬偵測器**（`BaselineDetector`），不是 OCR 模型。

`BaselineDetector` 有兩種模式：

- `oracle`：
  - 直接回傳 ground truth（等同完美辨識）
  - 用來檢查評估流程是否正常（sanity check）

- `noisy`：
  - 以 `error_rate` 機率隨機把箭值改成其他類別（例如把 `9` 改成 `7` 或 `M`）
  - 接著重新計算該靶位所有 end 的：
    - `subtotal`
    - `cumulative`
    - `total`
    - `x_count`
    - `x_plus_ten_count`
  - 目的是模擬「辨識有誤差」時最終評估數字的變化

支援類別：`X, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, M`

> 重點：目前的「偵測」不是從影像抽特徵，而是對既有標註資料做可控噪聲注入，用於驗證評估與報表流程。

---

## 3. 準確率怎麼算？

`evaluate_dataset()` 目前輸出兩種核心指標：

1. **Arrow Accuracy（箭值準確率）**
   - 分子：預測箭值 `pred_arrow.value` 與真值 `gt_arrow.value` 相同的箭數
   - 分母：全部箭數

2. **Total Accuracy（靶位總分準確率）**
   - 分子：每個 target 的 `pred_target.total == gt_target.total` 的靶位數
   - 分母：全部 target 數

另外也輸出 `per_sheet`：每張影像各自的 arrow / total accuracy。

---

## 4. 輸出檔案格式

預設輸出：`$OUTPUT_DIR/eval/detection_eval.json`

結構：

```json
{
  "summary": {
    "total_arrows": 14400,
    "correct_arrows": 12940,
    "arrow_accuracy": 0.8986,
    "total_targets": 400,
    "correct_totals": 221,
    "total_accuracy": 0.5525
  },
  "per_sheet": [
    {
      "image_id": "synthetic_000001",
      "arrow_accuracy": 0.9028,
      "total_accuracy": 0.5
    }
  ]
}
```

---

## 5. 使用方式

### A. 直接產生新假資料再跑評估

```bash
OUTPUT_DIR=./dataset/eval_run \
NUM_IMAGES=100 \
SEED=1234 \
DETECT_MODE=noisy \
ERROR_RATE=0.10 \
bash scripts/run_detection_workflow.sh
```

### B. 重用既有假資料（不重生）

```bash
MANIFEST=./dataset/eval_run/manifest.jsonl \
OUTPUT_DIR=./dataset/eval_run \
DETECT_MODE=oracle \
bash scripts/run_detection_workflow.sh
```

---

## 6. 如何保留未來「真實資料」彈性

目前已保留可替換介面：`predict_sheet(ground_truth: dict) -> dict`。

未來可改成：

1. 用真實資料清單（可維持 manifest 形式，或新增 reader）
2. 在 detector 內改為：
   - 讀影像
   - 呼叫 OCR/分類模型
   - 組出與現有 schema 相同的 prediction 結構
3. 評估端 `evaluate_dataset()` 幾乎可不變，直接沿用目前的比對與輸出流程

建議後續拆分為：

- `ModelDetector`（真實推論）
- `SyntheticNoiseDetector`（測試用）

透過參數切換 detector，便於 regression test 與真實場景共存。

---

## 7. 目前限制

- 尚未做影像層級偵測（無 bbox/segmentation/OCR cell extraction）
- 指標較基礎（未含 confusion matrix、per-class precision/recall/F1）
- 比對依賴 label schema 一致性，尚未納入資料清洗與容錯

以上是目前版本定位：先把**可重現、可量化、可替換**的評估骨架建立完成。

---

## 8. 回應：真實圖片歪斜/方向/陰影目前怎麼處理？

你提得完全正確：

- 先前 `BaselineDetector` 主要是**標註資料層**的模擬，沒有真正處理影像前處理問題。
- 因此你看不到針對「歪斜、方向不對、陰影」的影像處理是正常的。

這次補上了獨立的影像品質檢查模組：

- `src/score_reader/dataset/image_quality.py`
  - `estimated_skew_deg`：以 Hough line 估計傾斜角
  - `orientation`：估計 portrait / landscape
  - `shadow_ratio`：暗區比例（灰階 < 60）
  - `blur_score`：Laplacian 變異數（越低通常越糊）
- `scripts/run_real_image_quality_check.sh`
  - 針對真實資料夾批次輸出 `quality_report.json`

### 使用方式

```bash
IMAGES_DIR=./dataset/real_images \
OUTPUT_JSON=./dataset/real_images_quality/quality_report.json \
bash scripts/run_real_image_quality_check.sh
```

> 這一步是「真實資料檢測前」的品質閘門。後續可設定門檻（例如 skew > 8° 或 shadow_ratio > 0.25）先做校正或人工複核，再進入 OCR/辨識。
