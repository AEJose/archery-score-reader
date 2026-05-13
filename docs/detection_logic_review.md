# SheetRenderer 偵測邏輯 Review

> 原始檔案: `src/score_reader/dataset/generator/sheet_renderer.py`
> 模板圖片: `sample.png`（約 1100×820px，4 個計分表橫向排列）

---

## Pipeline 總覽

```
render()
  └─ _detect_cells(image)
       ├─ Step 1: 暗像素掃描 → dark_cols, dark_rows
       ├─ Step 2: _merge_lines() → v_lines, h_lines
       ├─ Step 3: _detect_target_regions() → 4 個計分區域 (left, top, right, bottom)
       └─ Step 4: 在每個 region 內切出 cell 格子
```

如果任何步驟失敗（lines < 8 或 regions ≠ 4），直接回傳空 list，
`render()` 就只會存一張空白模板。

---

## Step 1: 暗像素掃描（L38-53）

```python
# 垂直線偵測：逐欄掃描
for x in range(w):
    dark_count = sum(1 for y in range(h) if px[x, y] < 110)  # 門檻: 像素值 < 110
    if dark_count > h * 0.20:                                 # 門檻: 佔該欄 20% 以上
        dark_cols.append(x)

# 水平線偵測：逐列掃描
for y in range(h):
    dark_count = sum(1 for x in range(w) if px[x, y] < 110)  # 門檻: 像素值 < 110
    if dark_count > w * 0.20:                                 # 門檻: 佔該列 20% 以上
        dark_rows.append(y)
```

**硬編碼門檻：**
| 參數 | 值 | 用途 |
|---|---|---|
| 像素亮度 | `< 110` | 判定為「暗」的灰階門檻 |
| 佔比 | `> 0.20` (20%) | 一欄/一列中暗像素佔比超過此值才算「線」|

**潛在問題：**
- 逐像素 Python loop，對大圖效能差（可改用 numpy 向量化）
- 20% 門檻假設線條橫跨圖片寬/高的 20% 以上。若模板有較短的線段會漏掉；
  反之若有大面積暗色區域（如 X 打叉區域）可能誤判

---

## Step 2: _merge_lines()（L118-127）

```python
def _merge_lines(self, indices: list[int]) -> list[int]:
    groups: list[list[int]] = [[indices[0]]]
    for idx in indices[1:]:
        if idx - groups[-1][-1] <= 2:   # 門檻: 相鄰 ≤ 2px 視為同一條線
            groups[-1].append(idx)
        else:
            groups.append([idx])
    return [sum(g) // len(g) for g in groups]  # 取每組的平均位置
```

**硬編碼門檻：**
| 參數 | 值 | 用途 |
|---|---|---|
| 合併距離 | `<= 2` px | 相鄰暗像素列/欄距離 ≤ 2 就合併為一條線 |

**潛在問題：**
- 粗線（寬度 > 5px）會被拆成多條。對此模板問題不大，但遇到粗框線模板可能失準

---

## Step 3: _detect_target_regions()（L82-116）— 剛修改過

### 修改前（原始版本）的問題

原始邏輯找「相鄰兩條線之間 gap 260~520px」的大缺口，但此模板中：
- 相鄰 h_line 間距 ≈ 30~60px（每一列的行高）
- 相鄰 v_line 間距 ≈ 25~50px（每一欄的欄寬）

所有間距都遠小於門檻 → `regions = []` → 偵測全部失敗。

### 修改後（當前版本）

```python
# 1) 計算相鄰 v_line 間距
v_gaps = [v_lines[i+1] - v_lines[i] for i in range(len(v_lines) - 1)]
median_gap = sorted(v_gaps)[len(v_gaps) // 2]
split_threshold = max(median_gap * 2, 8)          # 門檻: 中位數 × 2，最少 8px

# 2) 依間距分群
groups: list[list[int]] = [[v_lines[0]]]
for i, gap in enumerate(v_gaps):
    if gap > split_threshold:                      # 超過門檻 → 新群組
        groups.append([v_lines[i + 1]])
    else:
        groups[-1].append(v_lines[i + 1])

# 3) 取 ≥ 5 條線的群組，按線數排序取前 4
table_groups = sorted(
    [g for g in groups if len(g) >= 5],            # 門檻: 至少 5 條垂直線
    key=lambda g: len(g), reverse=True,
)[:4]

# 4) 上下邊界 = h_lines 的首尾
top = h_lines[0]
bottom = h_lines[-1]
return [(g[0], top, g[-1], bottom) for g in table_groups]
```

**硬編碼門檻：**
| 參數 | 值 | 用途 |
|---|---|---|
| 分群倍率 | `median × 2` | 間距超過中位數 2 倍 → 判定為不同表格 |
| 最小分群門檻 | `8` px | 避免中位數太小導致過度分群 |
| 最少垂直線 | `>= 5` | 濾掉非計分表的小群組（如頁首方塊）|
| 最多群組數 | `4` | 此模板固定 4 位選手 |

**待確認 / 潛在問題：**
1. **top/bottom 用 h_lines 首尾** — 會把頁首（日期/賽事）和頁尾（記分員/裁判）
   的水平線也包進 region 範圍。目前靠 Step 4 的 cell 尺寸過濾來排除，
   但如果頁首 cell 尺寸恰好落在合法範圍內，會產生多餘的 cell。
2. **median × 2 可能不穩定** — 如果表間間隙恰好等於某些較寬欄位的寬度，
   分群會出錯。
3. **硬編碼 4 個群組** — 如果要支援 2 人/3 人的計分表，需要參數化。

---

## Step 4: Region 內切 Cell（L64-80）

```python
for left, top, right, bottom in regions:
    local_v = [x for x in v_lines if left <= x <= right]
    local_h = [y for y in h_lines if top <= y <= bottom]

    for r1, r2 in zip(local_h, local_h[1:]):
        row_h = r2 - r1
        if row_h < 22 or row_h > 110:       # 門檻: 行高 22~110px
            continue
        for c1, c2 in zip(local_v, local_v[1:]):
            col_w = c2 - c1
            if col_w < 24 or col_w > 170:    # 門檻: 欄寬 24~170px
                continue
            cells.append(Cell(c1 + 3, r1 + 3, c2 - 3, r2 - 3))  # 內縮 3px
```

**硬編碼門檻：**
| 參數 | 值 | 用途 |
|---|---|---|
| 行高下限 | `22` px | 太窄的行不是有效的計分列 |
| 行高上限 | `110` px | 太高的行不是有效的計分列 |
| 欄寬下限 | `24` px | 太窄的欄不是有效的計分欄 |
| 欄寬上限 | `170` px | 太寬的欄不是有效的計分欄 |
| 內縮 | `3` px | Cell 邊界向內縮 3px，避免框線被寫到 |

**潛在問題：**
1. **沒有語意分類** — 所有合法尺寸的 cell 一律加入，不區分「箭靶分數欄」、
   「小計欄」、「X/X+10 統計欄」、「姓名欄」等。後續 `_flatten_values` 按
   順序 zip 填入，如果偵測到的 cell 數量或順序不對，分數會填錯位置。
2. **排序只看 (top, left)** — 同一列中不同 region 的 cell 會交錯排列，
   而 `_flatten_values` 是按 target 順序展開的（先填完 target 0 全部，
   再 target 1…）。如果 4 個 region 的 cell 混在一起排，zip 對位就會錯。
3. **行高/欄寬門檻寫死** — 不同解析度的模板可能需要不同的值。

---

## 硬編碼門檻彙總

| 位置 | 參數 | 值 | 風險 |
|---|---|---|---|
| Step 1 L45-46 | 暗像素灰階 | `< 110` | 中：依賴模板對比度 |
| Step 1 L46,52 | 暗像素佔比 | `> 20%` | 中：短線段會漏掉 |
| Step 2 L123 | 合併距離 | `<= 2px` | 低：粗線可能拆開 |
| Step 3 L90-91 | 分群門檻 | `median×2, min 8` | 中：表間距≈欄寬時失準 |
| Step 3 L103 | 最少垂直線 | `>= 5` | 低 |
| Step 3 L106 | 最多群組 | `4` | 高：寫死選手數 |
| Step 3 L113-114 | 上下邊界 | h_lines 首尾 | 高：含頁首頁尾 |
| Step 4 L71 | 行高 | `22~110px` | 中：依賴模板尺寸 |
| Step 4 L75 | 欄寬 | `24~170px` | 中：依賴模板尺寸 |
| Step 4 L77 | 內縮 | `3px` | 低 |

---

## 最高優先修復建議

1. **Step 3 的 top/bottom** — 應改為只取計分區域的 h_lines 範圍，而非整張圖
2. **Step 4 的 cell 排序** — 應先按 region 分組，每個 region 內部再 (top, left) 排序，
   否則 `_flatten_values` 的 zip 對位會錯
