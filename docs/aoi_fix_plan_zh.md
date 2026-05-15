# 計分卡 AOI 與辨識流程修正建議（現階段落地版）

## 目標

將目前「大範圍 AOI + 直接 OCR」改為「卡片正規化 + 表格切格 + 單格辨識」，優先提升真實照片下的穩定性。

## 已調整（本次程式修正）

1. **單卡方向正規化（rotation normalize）**
   - 每張 target card 會嘗試 0/90/180/270 度。
   - 以表格線（水平 + 垂直）形態學響應總量作為評分，選擇最像「正常表格方向」的版本。
   - 目的是處理像 Target 4 這種方向不一致問題。

2. **score table 區域自動偵測（去除 metadata/簽名區干擾）**
   - 不再直接以整張卡做 cell 偵測。
   - 先從線段密集區找出 `score_table_bbox`，僅在此區域內切格。
   - 可降低姓名欄、備註欄、標註文字（如 E1A1）對辨識的污染。

3. **Artifacts 增加 score table 輸出**
   - pipeline artifacts 新增 `score_tables`，可直接做 debug overlay 與後續誤差分析。

## 建議的下一步（建議依序）

### P1. 單卡 perspective correction
- 目前已做方向正規化，但仍建議每張卡再做一次四點透視校正。
- 目的：讓格線更平行、切格邊界更穩。

### P2. 交點切格替代目前 cell heuristic
- 以 `vertical_lines × horizontal_lines` 交點裁切 cell。
- 每格由實際線段決定，不依賴固定比例。

### P3. 單格分類器（而非整區 OCR）
- 類別：`1~10, X, M, blank`。
- 在低信心時保留 top-k 候選，交給規則檢查器做最終決策。

### P4. 計分規則校驗器
- 每回合：前 3 箭小計、後 3 箭小計、回合積分。
- 全局：累計分數單調與加總一致性。
- 可回推低信心格（constraint-based correction）。

## 推薦資料輸出格式

```json
{
  "target_id": 1,
  "rotation": 90,
  "score_table_bbox": [x1, y1, x2, y2],
  "rounds": [
    {
      "round": 1,
      "arrows": ["10", "X", "9", "7", "6", "6"],
      "subtotals": [29, 19],
      "round_score": 48,
      "cumulative": 48,
      "validation": {
        "subtotal_ok": true,
        "round_ok": true,
        "cumulative_ok": true
      }
    }
  ]
}
```

## 一句話總結

AOI 不應直接服務 OCR；應先服務**表格結構化切格**，再做 cell-level 辨識與規則校驗。
