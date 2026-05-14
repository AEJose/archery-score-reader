# Debug Visualize 使用說明

`debug-visualize` 會輸出 OCR pipeline 的可視化疊圖，協助快速檢查「區域偵測、格線偵測、OCR 辨識」是否對齊。

## CLI

```bash
uv run python -m score_reader.cli debug-visualize \
  --image <image_path> \
  --output <output_dir>
```

## 輸出檔案

命令會在 `--output` 目錄產生 4 張圖：

- `step1_target_regions.png`：原圖 + 4 個 target 區域框（紅/綠/藍/黃）。
- `step2_cells.png`：step1 基礎上疊加每個偵測到的 cell 邊框（淺灰）。
- `step3_ocr_results.png`：step2 基礎上疊加 OCR token bbox 與 `文字 + 信心度` 標籤。
- `combined.png`：同 `step3_ocr_results.png`，提供單張快速 review。

## 標籤顏色規則

OCR 標籤背景依 confidence 分級：

- `>= 0.8`：綠色
- `0.5 ~ 0.79`：黃色
- `< 0.5`：紅色

## 典型用途

1. 驗證 target 區域是否正確框住 4 個選手欄位。
2. 驗證 cell 邊界是否貼合原始格線。
3. 快速發現 OCR 高錯誤區域（低信心度紅色標籤）。
