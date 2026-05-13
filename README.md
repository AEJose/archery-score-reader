# Archery Score Reader

[English](#english) | [中文](#中文)

---

## English

### Overview

A batch processing system for recognizing handwritten archery score sheets from photographs. The system extracts structured scoring data from images that may contain perspective skew, paper deformation, uneven lighting, shadows, blur, and red-pen corrections by judges.

The design goal is not fully automatic perfect OCR, but rather:

> Batch extraction + rule validation + confidence tracking + review item generation + extensible correction strategies + extensible report exporters.

### Score Sheet Format

Each score sheet contains **4 archers**. One round consists of **6 ends**, with **6 arrows per end**. The 6 arrows in each end are split into **two groups of 3**, each group with its own subtotal.

```
Score Sheet (Individual Qualifying)
┌─────────────────────────────────────────────┐
│ Date / Event                                │
├───────────┬───────────┬───────────┬─────────┤
│ Archer 1  │ Archer 2  │ Archer 3  │ Archer 4│
│ (target   │ (target   │ (target   │ (target │
│  block)   │  block)   │  block)   │  block) │
└───────────┴───────────┴───────────┴─────────┘

Per Target Block:
  Header: Unit (school/company/org), Name, Target No.
  Columns: Arrow 1 | Arrow 2 | Arrow 3 | Subtotal | End Score | Cumulative

Per End (2 rows):
  Row 1: arrows 1-3 → subtotal (top 3)
  Row 2: arrows 4-6 → subtotal (bottom 3)
  End score = sum of both subtotals (max 60)

Per Archer:
  6 ends × 6 arrows = 36 arrows
  Max score per arrow: 10 (or X)
  Max total: 6 × 60 = 360

Footer: X count, X+10 count, Total, Archer signature
Sheet footer: Scorer signature, Judge signature
```

### Features

- **Batch Processing** — Process an entire folder of score sheet images in one run
- **Multi-target Support** — One image can contain multiple player/target blocks
- **Error Isolation** — A single failed image does not stop the entire batch
- **Arrow Score Recognition** — Recognizes X, 10, 9, 8, ..., 1, M, blank
- **Red-pen Correction Detection** — Detects judge corrections (strike-through, overwrite, circle, etc.)
- **Rule-based Validation** — Cross-checks subtotals, cumulative scores, X counts, and totals
- **Confidence Tracking** — Every recognized value carries a confidence score and top-k candidates
- **Review Item Generation** — Flags uncertain results for efficient human review
- **Extensible Correction Strategies** — Strategy Pattern + Chain of Responsibility; add new strategies without modifying the core pipeline
- **Extensible Report Exporters** — Add new output formats without modifying the core pipeline
- **Synthetic Data Pipeline** — Generate augmented training data with configurable parameters

### Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Package Manager | uv |
| CV / Image | OpenCV, Pillow, scikit-image |
| ML Inference | ONNX Runtime |
| Data Models | Pydantic |
| CLI | Typer + Rich |
| Data Export | Pandas |
| Config | PyYAML |
| Training (optional) | PyTorch, Albumentations |

### Supported Platforms

- macOS (including Apple Silicon)
- Windows 10/11
- Linux x86_64

### Outputs

| File | Description |
|---|---|
| `raw_player_scores.csv` | One row per arrow — the most granular score table |
| `total_scores.csv` | One row per player/target — summary with totals, X counts, validation status |
| `recognition_results.json` | Full structured recognition result for downstream integration |
| `review_items.csv` | Cells requiring human review, with confidence, candidates, and crop paths |
| `debug/` | Debug overlay images and cell crops |

### Quick Start

```bash
# Install dependencies
uv sync

# Run recognition on a folder of images
uv run score-reader run --input ./input --output ./output --config ./configs/default.yaml

# Generate synthetic training data
uv run score-reader generate-dataset \
  --template ./templates/score_sheet.png \
  --geometry ./templates/score_sheet_geometry.json \
  --output ./dataset/generated \
  --config ./configs/augmentation.yaml

# Validate generated dataset
uv run score-reader validate-dataset --dataset ./dataset/generated

# Print resolved config
uv run score-reader print-config --config ./configs/default.yaml
```

### Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy src
```

### Processing Pipeline

```
Folder Scanner
  -> Image Loader
  -> Quality Checker
  -> Document Detector
  -> Perspective Corrector
  -> Template Registrar
  -> Target Block Extractor
  -> Cell Extractor
  -> Cell Classifier
  -> Red Mark Detector
  -> Rule Validator
  -> Correction Pipeline
  -> Structured Result
-> Report Exporters
```

### Project Structure

```
score-reader/
  pyproject.toml
  configs/                  # YAML configuration files
  templates/                # Score sheet templates and geometry definitions
  assets/                   # Fonts, textures, shadow masks
  src/score_reader/
    cli.py                  # Typer CLI entry point
    config/                 # Settings and config loading
    domain/                 # Pydantic models, score types, errors
    input/                  # Folder scanning
    image/                  # Loading, quality check, detection, correction
    extraction/             # Target block and cell extraction
    recognition/            # Cell classification, red mark detection
    validation/             # Score calculation, rule validation
    correction/             # Correction strategy pipeline and registry
    export/                 # Report exporter pipeline and registry
    dataset/                # Synthetic data generation pipeline
    pipeline/               # Job runner and image processor
  tests/
    unit/
    integration/
    golden/                 # Fixed sample images and expected outputs
    e2e/
```

### Implementation Phases

| Phase | Scope |
|---|---|
| 1 | Project skeleton, domain models, score calculator, strategy/exporter interfaces |
| 2 | All exporters with fake recognition results |
| 3 | Synthetic data pipeline MVP |
| 4 | ONNX cell classifier integration |
| 5 | Full sheet processing MVP (image loading through end-to-end batch) |
| 6 | Red-pen detection and rule correction strategies |

### License

TBD

---

## 中文

### 概述

批次處理手寫射箭計分表照片的辨識系統。系統從影像中擷取結構化的分數資料，影像可能包含透視歪斜、紙張變形、光線不均、陰影、模糊，以及裁判的紅筆修改。

設計目標並非全自動完美 OCR，而是：

> 批次擷取 + 規則驗證 + 信心度追蹤 + 待審項目產生 + 可擴充修正策略 + 可擴充報表匯出。

### 計分表格式

每張計分表包含 **4 位選手**。一局共 **6 輪（end）**，每輪射 **6 支箭**。每輪的 6 支箭分為**上下兩組各 3 箭**，各有獨立小計。

```
計分表（個人資格賽）
┌─────────────────────────────────────────────┐
│ 日期 / 賽事                                  │
├───────────┬───────────┬───────────┬─────────┤
│ 選手 1    │ 選手 2    │ 選手 3    │ 選手 4  │
│（靶位區塊）│（靶位區塊）│（靶位區塊）│（靶位區塊）│
└───────────┴───────────┴───────────┴─────────┘

每個靶位區塊：
  表頭：單位（學校/公司/機構）、姓名、靶位號
  欄位：箭 1 | 箭 2 | 箭 3 | 小計 | 得分 | 累計

每輪（佔 2 行）：
  第 1 行：第 1~3 箭 → 小計（上半輪）
  第 2 行：第 4~6 箭 → 小計（下半輪）
  得分 = 兩組小計之和（滿分 60）

每位選手：
  6 輪 × 6 箭 = 36 箭
  每箭最高分：10（或 X）
  一局滿分：6 × 60 = 360

底部：X 數、X+10 數、總計、選手簽名
頁尾：記分員簽名、裁判簽名
```

### 功能特點

- **批次處理** — 一次處理整個資料夾的計分表影像
- **多靶位支援** — 一張影像可包含多個選手/靶位區塊
- **錯誤隔離** — 單張影像失敗不會中斷整批作業
- **箭支分數辨識** — 辨識 X、10、9、8、...、1、M、空白
- **紅筆修改偵測** — 偵測裁判修改（刪除線、覆寫、圈選等）
- **規則驗證** — 交叉檢查小計、累計分數、X 數與總分
- **信心度追蹤** — 每個辨識值都帶有信心度分數與前 k 個候選值
- **待審項目產生** — 標記不確定的結果以便高效人工複查
- **可擴充修正策略** — 策略模式 + 責任鏈；新增策略無需修改核心管線
- **可擴充報表匯出** — 新增輸出格式無需修改核心管線
- **合成資料管線** — 以可配置參數產生增強訓練資料

### 技術棧

| 元件 | 技術 |
|---|---|
| 語言 | Python 3.11+ |
| 套件管理 | uv |
| 影像處理 | OpenCV、Pillow、scikit-image |
| 推論引擎 | ONNX Runtime |
| 資料模型 | Pydantic |
| 命令列 | Typer + Rich |
| 資料匯出 | Pandas |
| 設定檔 | PyYAML |
| 訓練（選用） | PyTorch、Albumentations |

### 支援平台

- macOS（含 Apple Silicon）
- Windows 10/11
- Linux x86_64

### 輸出檔案

| 檔案 | 說明 |
|---|---|
| `raw_player_scores.csv` | 每箭一列 — 最細粒度的分數表 |
| `total_scores.csv` | 每位選手一列 — 含總分、X 數、驗證狀態的摘要表 |
| `recognition_results.json` | 完整結構化辨識結果，供下游系統整合 |
| `review_items.csv` | 需人工複查的儲存格，含信心度、候選值與裁切圖路徑 |
| `debug/` | 除錯用的疊加影像與儲存格裁切圖 |

### 快速開始

```bash
# 安裝依賴
uv sync

# 對影像資料夾執行辨識
uv run score-reader run --input ./input --output ./output --config ./configs/default.yaml

# 產生合成訓練資料
uv run score-reader generate-dataset \
  --template ./templates/score_sheet.png \
  --geometry ./templates/score_sheet_geometry.json \
  --output ./dataset/generated \
  --config ./configs/augmentation.yaml

# 驗證產生的資料集
uv run score-reader validate-dataset --dataset ./dataset/generated

# 輸出解析後的設定
uv run score-reader print-config --config ./configs/default.yaml
```

### 開發指令

```bash
# 安裝開發依賴
uv sync --extra dev

# 執行測試
uv run pytest

# 程式碼檢查
uv run ruff check .

# 格式化
uv run ruff format .

# 型別檢查
uv run mypy src
```

### 處理管線

```
資料夾掃描
  -> 影像載入
  -> 品質檢查
  -> 文件偵測
  -> 透視校正
  -> 模板配準
  -> 靶位區塊擷取
  -> 儲存格擷取
  -> 儲存格分類
  -> 紅筆偵測
  -> 規則驗證
  -> 修正策略管線
  -> 結構化結果
-> 報表匯出
```

### 專案結構

```
score-reader/
  pyproject.toml
  configs/                  # YAML 設定檔
  templates/                # 計分表模板與幾何定義
  assets/                   # 字型、紙張材質、陰影遮罩
  src/score_reader/
    cli.py                  # Typer CLI 進入點
    config/                 # 設定載入
    domain/                 # Pydantic 模型、分數型別、錯誤定義
    input/                  # 資料夾掃描
    image/                  # 載入、品質檢查、偵測、校正
    extraction/             # 靶位區塊與儲存格擷取
    recognition/            # 儲存格分類、紅筆偵測
    validation/             # 分數計算、規則驗證
    correction/             # 修正策略管線與註冊表
    export/                 # 報表匯出管線與註冊表
    dataset/                # 合成資料產生管線
    pipeline/               # 作業執行器與影像處理器
  tests/
    unit/
    integration/
    golden/                 # 固定樣本影像與預期輸出
    e2e/
```

### 實作分期

| 階段 | 範圍 |
|---|---|
| 1 | 專案骨架、領域模型、分數計算器、策略/匯出器介面 |
| 2 | 以假辨識結果完成所有匯出器 |
| 3 | 合成資料管線 MVP |
| 4 | ONNX 儲存格分類器整合 |
| 5 | 完整計分表處理 MVP（影像載入到端到端批次執行） |
| 6 | 紅筆偵測與規則修正策略 |

### 授權

待定

---

## Project Init + Generate 100 Fake Samples

### One-command way (recommended)

```bash
bash ./scripts/init_and_generate_100.sh
```

This script will:
1. install dependencies via `uv sync`
2. generate 100 fake samples based on `./sample.png`
3. write outputs to `./dataset/generated`

### Manual commands

```bash
uv sync
uv run score-reader generate-dataset \
  --template ./sample.png \
  --output ./dataset/generated \
  --num-images 100 \
  --seed 1234
```

---

## 專案初始化 + 一個指令生成 100 筆假資料

### 一鍵方式（建議）

```bash
bash ./scripts/init_and_generate_100.sh
```

這個腳本會：
1. 用 `uv sync` 安裝依賴
2. 以 `./sample.png` 為基底生成 100 筆假資料
3. 輸出到 `./dataset/generated`

### 手動指令

```bash
uv sync
uv run score-reader generate-dataset \
  --template ./sample.png \
  --output ./dataset/generated \
  --num-images 100 \
  --seed 1234
```
