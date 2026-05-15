# Archery Score Reader：現有程式架構整理

## 1) 模組分層

- `src/score_reader/processing`
  - 負責影像前處理、AOI 偵測、表格切格、流程編排。
- `src/score_reader/recognition`
  - OCR 引擎與資料模型（`ArrowReading`、`EndReading`、`TargetReading`、`StructuredScoreSheet`）。
- `src/score_reader/visualization`
  - debug overlay / 可視化輸出。
- `src/score_reader/cli.py`
  - 命令列入口，串接整體流程。
- `tests/`
  - 單元測試與 fixture。

## 2) 目前核心流程（Parser Pipeline）

入口：`ScoreSheetParser.parse_with_artifacts(image_path)`

1. 讀圖與整頁修正
   - `_correct_image`：嘗試多方向旋轉 + deskew + perspective warp，挑出能偵測最多 target region 的版本。
2. 偵測 target card 粗區域
   - `SheetRenderer._detect_target_regions(gray)`。
3. 每張 card 交給 `CardRegionProcessor`
   - 卡片方向正規化（0/90/180/270）
   - 自動找 `score_table_bbox`
   - 只在 score table 內偵測格線/cell
   - 切出箭值 cell 並做 OCR token normalize
4. 組裝 domain model
   - 每 6 箭組成一回合 (`EndReading`)
   - 加總回合 subtotal 與 target total
5. 輸出
   - `StructuredScoreSheet`
   - `PipelineArtifacts`（含 target regions、rows、arrow cells、score table bbox）

## 3) 這次 refactor 重點（God Object 拆分）

原先 `ScoreSheetParser` 同時負責：
- 整頁修正
- 單卡正規化
- 表格區定位
- cell 偵測
- OCR 讀值
- domain 組裝

現已拆出 `CardRegionProcessor`，將「單卡內部流程」集中：
- `process(...)`
- `_normalize_card_orientation(...)`
- `_detect_score_table_bbox(...)`
- `_detect_cells(...)`
- `_fallback_detect_lines(...)`
- `_classify_arrow_cells(...)`
- `_read_arrows(...)`

`ScoreSheetParser` 目前只保留：
- 流程編排（orchestration）
- 整頁幾何修正
- 結果組裝

## 4) 主要資料結構

- `PipelineArtifacts`
  - `corrected_bgr`
  - `target_regions`
  - `target_rows`
  - `arrow_cells`
  - `score_tables`
- `CardProcessingResult`
  - `rows`
  - `arrow_cells`
  - `arrows`
  - `score_table_bbox`

## 5) 現階段限制與後續建議

- 已改善：
  - 方向不一致（如 target 4）
  - 大 AOI 混入 metadata 的問題
- 尚可強化：
  1. 單卡 perspective correction（每張卡再做四點校正）
  2. 以交點切格（intersection-based cell segmentation）
  3. cell classifier + checksum validation（小計/累計約束）

