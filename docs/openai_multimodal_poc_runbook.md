# OpenAI 多模態辨識 POC：執行說明

## 1) 前置準備

1. 安裝依賴

```bash
uv sync
```

2. 設定 API Key（支援 `.env`）

方式 A：Shell 環境變數

```bash
export OPENAI_API_KEY="<YOUR_API_KEY>"
```

方式 B：在專案根目錄建立 `.env`（推薦給無法 `export` 的執行環境）

```dotenv
OPENAI_API_KEY=<YOUR_API_KEY>
```

## 2) 單張圖片辨識

```bash
scripts/run_openai_ocr_poc.sh ./path/to/one_image.jpg
```

可選參數（依序）：

```bash
scripts/run_openai_ocr_poc.sh <input> <output_csv> <output_json> <model>
```

範例：

```bash
scripts/run_openai_ocr_poc.sh ./sample.png ./out/sample.csv ./out/sample.json gpt-5.5
```

## 3) 整個資料夾辨識

```bash
scripts/run_openai_ocr_poc.sh ./path/to/folder ./out/folder.csv ./out/folder.json gpt-5.5
```

會自動掃描資料夾第一層中支援的圖片格式：`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff`。

## 4) 輸出內容

- `CSV`（預設 `./out/openai_ocr.csv`）：每位選手一列（一個 row 包含 1~6 End 全資訊），欄位包含：
  - 圖檔路徑、選手序號、單位、靶道、lane_code（如 1A/2F/3C）、姓名
  - `end1`~`end6`：每個 end 的上半 3 箭/小計、下半 3 箭/小計、end total、cumulative total
  - 該選手最終總分
  - notes（模型不確定或缺漏說明）
- `JSON`（預設 `./out/openai_ocr.json`）：完整結構化辨識結果，方便後續二次處理。

## 5) 注意事項

- 這是 POC，核心目標是「一口氣跑通 + 輸出完整結構」。
- 若影像品質、角度、遮蔽較差，欄位可能為 `null`，並會在 `notes` 提示。
- 若要提升穩定性，可先做影像前處理（裁切、旋轉校正、對比增強）。


## 6) 旋轉校正（已內建）

POC 使用傳統 CV 先看長寬比再決定最小旋轉候選：
- 直式（height > width）：只嘗試 90° / 270°
- 橫式或近似方形（width >= height）：只嘗試 0° / 180°

再從候選中挑選結構最完整的結果，可改善直式轉橫式與上下顛倒情境，同時降低模型呼叫成本。


## 7) Review 範例輸出

已提供可直接檢視的範例輸出（依照目前程式輸出欄位設計）：

- `docs/openai_poc_sample_output.json`
- `docs/openai_poc_sample_output.csv`

可用以下命令快速查看：

```bash
cat docs/openai_poc_sample_output.json
cat docs/openai_poc_sample_output.csv
```


## 8) 空值與棄賽容忍度

- 一張計分紙可只有部分人數（例如僅 2~3 人）
- 每位選手的 `ends` 允許少於 6（例如中途棄賽、只填到 end3）
- CSV 仍固定輸出 `end1`~`end6` 欄位：缺少的 end 會留空（箭值空字串，其餘欄位為空值）
- 模型不確定的欄位會保留為 `null`，並在 `notes` 補充


## 9) 姓名、靶道、單位缺漏容忍

- 若測試資料缺少選手姓名、靶道、單位（或 lane_code），系統會容忍並輸出 `null`。
- 即使身份欄位缺漏，仍會盡量抽取每個 end 的箭值、小計、end total、累積總分。
- CSV 中對應欄位會留空，不會中斷整張表的輸出。


## 10) 圖片尺寸正規化（省成本）

- 系統會在送入模型前先做尺寸正規化：**最長邊不超過 2000 px**。
- 若原圖最長邊已小於或等於 2000 px，則維持原樣。
- 若有縮圖，`notes` 會附上 `resized_long_edge_to<=2000`。


## 11) Early-exit 角度策略（省成本）

- 每張圖仍先由長寬比決定兩個候選角度（直式: 90/270，橫式: 0/180）。
- 先只跑第一個角度：
  - 若結果品質已足夠（例如有身份欄位、且各選手大致有足夠 end 結構），就直接 early-exit，不再跑第二個角度。
  - 若品質不足，才跑第二個角度並擇優。
- 若觸發 early-exit，`notes` 會有 `early_exit_after_first_rotation`。


## 12) `.env` 載入機制

- CLI 執行時會自動呼叫 `load_dotenv()`，因此會嘗試載入目前工作目錄（含父層）可找到的 `.env`。
- 若同時有 shell 環境變數與 `.env`，預設以既有 shell 環境變數為優先。
