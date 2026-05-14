# fake_data_sample2.png 偵測分析報告

> 使用更新版 `sheet_renderer.py` 對 `fake_data_sample2.png` 跑完整偵測流程的分析結果。
> 本文件供後續 agent 作為修正依據。

---

## 1. 測試對象

| 項目 | 值 |
|------|-----|
| 影像檔案 | `fake_data_sample2.png`（專案根目錄） |
| 影像類型 | 合成假資料（由 pipeline 產生，帶有拍攝模擬 artifact） |
| 尺寸 | 1100 × 769 px |
| 方向 | landscape（橫向） |
| 記分區數量 | 4 個 |

---

## 2. 影像品質分析

```json
{
  "width": 1100,
  "height": 769,
  "estimated_skew_deg": 4.111,
  "orientation": "landscape",
  "shadow_ratio": 0.0245,
  "blur_score": 5726.489
}
```

| 指標 | 值 | 判定 |
|------|-----|------|
| 歪斜角度 | **+4.11°** | 中等歪斜，需校正 |
| 陰影比率 | 2.45% | 良好 |
| 模糊分數 | 5726.5 | 清晰 |

---

## 3. 新版程式碼的改動摘要

相較於上一版，`sheet_renderer.py` 新增/修改了以下核心邏輯：

| 元件 | 改動 | 狀態 |
|------|------|------|
| `_detect_cells` | 嘗試 4 個旋轉方向（0°/90°/180°/270°），選最佳結果 | 新增 |
| `_detect_cells_for_orientation` | 將原本的 `_detect_cells` 主體拆出，改用逐區域偵測 | 重構 |
| `_remap_cells_to_original` | 將旋轉後的 cell 座標映射回原始座標系 | 新增 |
| `_detect_region_grid_lines` | **逐區域**做格線偵測（adaptive threshold + morphological） | **新增（核心）** |
| `_detect_target_regions` | 加入長寬比過濾（>1.1）、fill ratio 過濾（>0.45）、去重、RETR_EXTERNAL | 改進 |
| `_dedupe_regions` | IoU > 0.75 的重疊區域去重 | 新增 |
| 硬編碼 `len(regions) != 4` | **已移除** — 現在接受任意數量 region | 修正 |

---

## 4. 區域偵測結果：通過

**4 個區域全部正確偵測，表頭不再被誤判。**

| 區域 | 座標 | 尺寸 | 長寬比 | 判定 |
|------|------|------|--------|------|
| R0 | (94,150)→(360,570) | 266×420 | 1.58 | 正確 |
| R1 | (343,171)→(602,587) | 259×416 | 1.61 | 正確 |
| R2 | (588,190)→(839,603) | 251×413 | 1.65 | 正確 |
| R3 | (829,210)→(1074,618) | 245×408 | 1.67 | 正確 |

### 與上版比較

| | 上版（real.png） | 新版（fake_data_sample2.png） |
|--|-----------------|------------------------------|
| 偵測數 | 4（含 1 誤判） | 4（全部正確） |
| 表頭誤判 | 有 | **無**（被 aspect < 1.1 過濾） |
| 去重 | 無 | 有（`_dedupe_regions`） |

### 對照：sample.png（乾淨模板）

| | sample.png | fake_data_sample2.png |
|--|-----------|----------------------|
| 偵測數 | 4 | 4 |
| 全部正確 | 是 | 是 |

**結論：區域偵測的改進有效。**

---

## 5. 格線偵測結果：失敗

**所有 4 個區域的格線偵測均回傳 0 條線，導致 0 cells 被偵測到。**

```
rot_k=0: 0 targets, 0 total cells
rot_k=1: 0 targets, 0 total cells
rot_k=2: 0 targets, 0 total cells
rot_k=3: 0 targets, 0 total cells
```

### 對照：sample.png

```
sample.png → R0: V=8 H=17 → 90 cells/target → 完美偵測
```

---

## 6. 格線偵測失敗根因分析

### 6.1 投影值 vs 閾值

`_detect_region_grid_lines` 的判定邏輯：

```python
v_candidates = np.where(v_proj > h * 0.18)[0]   # 垂直線閾值
h_candidates = np.where(h_proj > w * 0.22)[0]   # 水平線閾值
```

各區域實測數據：

| 區域 | V 閾值 | V 實際最大值 | V 達標率 | H 閾值 | H 實際最大值 | H 達標率 |
|------|--------|-------------|---------|--------|-------------|---------|
| R0 | 75.6 | **66.0** | 87.3% | 58.5 | **58.0** | 99.1% |
| R1 | 74.9 | **73.0** | 97.5% | 57.0 | **53.0** | 93.0% |
| R2 | 74.3 | **73.0** | 98.2% | 55.2 | **53.0** | 96.0% |
| R3 | 73.4 | **72.0** | 98.1% | 53.9 | **52.0** | 96.5% |

**所有區域的投影值都差一點點就能通過閾值，但全部 miss。**

- R0 的 H 投影差距最小：58.0 vs 58.5（差 0.5，即 **0.9%**）
- R1 的 V 投影差距最小：73.0 vs 74.9（差 1.9，即 **2.5%**）

### 6.2 根本原因：歪斜稀釋投影信號

影像有 **+4.11° 歪斜**（來自 `_apply_affine_jitter` 的模擬旋轉）。

投影法假設格線是完美的水平/垂直線。當格線歪斜 θ 度：

- 一條高 H 的垂直線，其像素會分散到 `H × tan(θ)` 個不同的 x 座標
- 例如 H=420, θ=4° → 分散到 **29 個 x 座標**
- 原本集中在 1 個 x 的投影值（最高 420），被稀釋為每個 x 只有 ~14–66

投影稀釋的量化影響：

```
理想（0° 歪斜）: V 投影最大值 ≈ H = 420 → 通過 0.18 × 420 = 75.6 ✓
實際（4° 歪斜）: V 投影最大值 = 66         → 未通過 75.6              ✗
稀釋率: 66 / 420 = 15.7%（閾值要求 18%）
```

### 6.3 Morphological 結果觀察

debug 影像分析（Region 0）：

| 步驟 | 檔案 | 觀察 |
|------|------|------|
| Adaptive threshold | `debug_region0_binary.png` | 格線和文字都有被偵測到 |
| Vertical morphology | `debug_region0_vertical.png` | 垂直線**碎片化** — 因歪斜被打斷成短段 |
| Horizontal morphology | `debug_region0_horizontal.png` | 水平線**碎片化** — 不連續片段 |

morphological opening 用的 kernel 尺寸：
- V kernel: `(1, 26)` — 要求連續 26px 的垂直白點
- H kernel: `(22, 1)` — 要求連續 22px 的水平白點

歪斜 4° 時，26px 垂直段會水平偏移 `26 × tan(4°) ≈ 1.8px`，這在 1px kernel 寬度下剛好會斷裂。

### 6.4 降低閾值的效果

即使降低投影閾值，偵測到的格線數量仍然不足：

| 閾值組合 | R0 V/H | R1 V/H | R2 V/H | R3 V/H | 需要 |
|---------|--------|--------|--------|--------|------|
| v=0.18, h=0.22（現行） | 0/0 | 0/0 | 0/0 | 0/0 | V≥7, H≥15 |
| v=0.15, h=0.20 | 2/1 | 3/1 | 3/1 | 2/1 | V≥7, H≥15 |
| v=0.12, h=0.18 | 3/1 | 3/1 | 3/1 | 2/1 | V≥7, H≥15 |
| v=0.10, h=0.15 | 3/1 | 3/2 | 3/2 | **7**/1 | V≥7, H≥15 |

**結論：僅降低閾值無法解決問題。** 投影法在 ≥4° 歪斜下的信號太弱，格線碎片化嚴重。

---

## 7. 問題定位總結

```
Pipeline 狀態：

[Step] 自動旋轉（0°/90°/180°/270°）     ✅ 正常運作
[Step] 區域偵測（contour + aspect filter） ✅ 正確找到 4 個記分區
[Step] 格線偵測（morphological + projection）❌ 全部失敗
  └─ 原因：4° 歪斜 → morphological 碎片化 + 投影稀釋
[Step] Cell 組裝                           ❌ 因格線為空而跳過
[Step] 文字放置                            ❌ 因 cell 為空而跳過
```

---

## 8. 修正建議

### 方案 A：先做歪斜校正（推薦）

在 `_detect_cells_for_orientation` 的開頭加入 deskew 步驟：

```python
def _detect_cells_for_orientation(self, arr: np.ndarray) -> list[list[Cell]]:
    arr = self._deskew(arr)  # ← 新增
    regions = self._detect_target_regions(arr)
    ...

def _deskew(self, gray: np.ndarray) -> np.ndarray:
    """Estimate skew angle via Hough lines and rotate to correct."""
    edges = cv2.Canny(gray, 80, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 120, minLineLength=80, maxLineGap=12)
    if lines is None:
        return gray
    angles = []
    for line in lines[:, 0]:
        x1, y1, x2, y2 = line
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if -45 <= angle <= 45:
            angles.append(angle)
    if not angles:
        return gray
    median_angle = float(np.median(angles))
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w/2, h/2), median_angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)
```

**優點**：
- 邏輯已存在於 `image_quality._estimate_skew_angle()`，可直接複用
- 修正後所有下游邏輯（morphological + projection）不需調整
- 一次修正同時解決 V 和 H 兩個方向的問題

**注意**：
- deskew 後需重新偵測 regions（因為 bounding box 會改變）
- 或者在每個 region 內部做局部 deskew

### 方案 B：加寬 Morphological kernel

將垂直 kernel 從 `(1, h//16)` 加寬為 `(3, h//16)` 以容忍小角度歪斜：

```python
v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, max(12, h // 16)))
```

**優點**：改動最小
**缺點**：只能容忍 ~2° 歪斜，超過仍會失敗；且會增加誤偵測（把文字筆畫當格線）

### 方案 C：改用 HoughLinesP 偵測格線

不依賴投影，直接用 Hough 線段偵測：

```python
def _detect_region_grid_lines_hough(self, gray, left, top, right, bottom):
    region = gray[top:bottom, left:right]
    edges = cv2.Canny(region, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=30, maxLineGap=10)
    # 將線段按角度分為水平組（|angle| < 15°）和垂直組（|angle - 90°| < 15°）
    # 每組內按 intercept 聚類，得到格線位置
    ...
```

**優點**：天然容忍歪斜（Hough 本身就是角度-距離空間）
**缺點**：實作較複雜，需要聚類邏輯

### 建議優先順序

1. **方案 A（deskew）**— 最小侵入、效果最好、邏輯已有原型
2. 方案 C（HoughLinesP）— 作為 A 不足時的備案
3. 方案 B（寬 kernel）— 快速驗證用，不建議作為正式方案

---

## 9. 預期修正後的效果

以 `sample.png`（0° 歪斜）的偵測結果作為目標基準：

| 指標 | sample.png（基準） | fake_data_sample2.png（現狀） | 修正後預期 |
|------|-------------------|------------------------------|-----------|
| Region 偵測 | 4 ✅ | 4 ✅ | 4 ✅ |
| 每區 V lines | 8 | 0 | ~7–8 |
| 每區 H lines | 17 | 0 | ~15–17 |
| 每區 cells | 90 | 0 | ~84–90 |
| 每區 rows | 15 | 0 | ~13–15 |

---

## 10. 驗證方式

修正完成後，用以下方式驗證：

```python
from PIL import Image
from score_reader.dataset.generator.sheet_renderer import SheetRenderer

renderer = SheetRenderer(seed=42)

# 1. 乾淨模板必須仍然正常
cells_clean = renderer._detect_cells(Image.open("sample.png").convert("RGB"))
assert len(cells_clean) == 4
assert all(len(c) >= 84 for c in cells_clean)

# 2. 帶 artifact 的假資料也要能偵測
cells_fake = renderer._detect_cells(Image.open("fake_data_sample2.png").convert("RGB"))
assert len(cells_fake) >= 3  # 至少 3 個區域
assert all(len(c) >= 60 for c in cells_fake)  # 每區至少 60 cells
```

也可對既有的 100 張合成資料做批次測試，統計成功率：

```bash
uv run python -c "
from pathlib import Path
from PIL import Image
from score_reader.dataset.generator.sheet_renderer import SheetRenderer

renderer = SheetRenderer(seed=42)
images = sorted(Path('dataset/generated/images/train').glob('*.png'))
success = 0
for img_path in images:
    cells = renderer._detect_cells(Image.open(img_path).convert('RGB'))
    if len(cells) >= 3 and all(len(c) >= 60 for c in cells):
        success += 1
print(f'Detection success: {success}/{len(images)}')
"
```
