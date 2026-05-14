# v_sample.png 偵測分析報告

> 使用更新版 `sheet_renderer.py` 對直式（portrait）合成影像跑偵測的分析結果。
> 本文件供後續 agent 作為修正依據。

---

## 1. 測試對象

| 項目 | 值 |
|------|-----|
| 影像檔案 | `tests/fixtures/v_sample.png` |
| 影像類型 | 合成假資料（pipeline 產生，帶 artifact + 90° 方向變換） |
| 尺寸 | 769 × 1100 px |
| 方向 | **portrait**（直式） |
| 記分區數量 | 4 個（其中 1 個因旋轉+裁切後偵測不到，實際可用 3 個） |

### 與其他測試影像的比較

| | sample.png（模板） | fake_data_sample2.png | v_sample.png |
|--|-------------------|----------------------|-------------|
| 方向 | landscape | landscape | **portrait** |
| 歪斜 | 0° | 4.1° | **-8.0°** |
| 方向變換 | 無 | 無 | **有（90° 旋轉）** |
| 記分區可偵測數 | 4 | 4 | 3 |

---

## 2. 影像品質分析

```json
{
  "width": 769,
  "height": 1100,
  "estimated_skew_deg": -7.977,
  "orientation": "portrait",
  "shadow_ratio": 0.0142,
  "blur_score": 3814.033
}
```

| 指標 | 值 | 判定 |
|------|-----|------|
| 歪斜角度 | **-7.98°** | 接近 8° 拒絕門檻，嚴重歪斜 |
| 陰影比率 | 1.42% | 良好 |
| 模糊分數 | 3814 | 清晰 |

---

## 3. 區域偵測結果

### 3.1 各旋轉方向偵測結果

| rot_k | 等效方向 | 偵測到的區域數 | 判定 |
|-------|---------|-------------|------|
| 0 | portrait (原始) | 1 | 不佳 — 只抓到 1 個窄長區域 |
| **1** | **landscape (順時針 90°)** | **3** | **最佳** |
| 2 | portrait (180°) | 1 | 不佳 |
| **3** | **landscape (逆時針 90°)** | **3** | 等效 rot_k=1 的鏡像 |

### 3.2 最佳旋轉（rot_k=1）的區域

| 區域 | 座標 | 尺寸 | 長寬比 | 判定 |
|------|------|------|--------|------|
| R0 | (30,205)→(295,629) | 265×424 | 1.60 | 正確 |
| R1 | (528,151)→(792,569) | 264×418 | 1.58 | 正確 |
| R2 | (744,125)→(1035,540) | 291×415 | 1.43 | 正確 |

debug 視覺化：`tests/fixtures/debug_output/v_sample_regions_rotk1.png`

**注意**：第 4 個記分區因強旋轉（~8°）被推出可視範圍或面積不足而未被偵測到。

**結論：自動旋轉 + 區域偵測機制正常運作。**

---

## 4. 格線偵測結果：全部失敗

```
所有 4 個 rot_k 方向：0 targets, 0 total cells
```

### 4.1 投影值 vs 閾值（rot_k=1 的 3 個區域）

| 區域 | V 最大投影 | V 閾值 | V 達標率 | H 最大投影 | H 閾值 | H 達標率 |
|------|----------|--------|---------|----------|--------|---------|
| R0 | **16** | 76 | **21%** | **23** | 58 | **39%** |
| R1 | **16** | 75 | **21%** | **25** | 58 | **43%** |
| R2 | **18** | 75 | **24%** | **25** | 64 | **39%** |

### 4.2 與 fake_data_sample2.png 的比較

| | fake_data_sample2 (4°歪斜) | v_sample (8°歪斜) |
|--|---------------------------|-------------------|
| V 達標率 | 87–98% | **21–24%** |
| H 達標率 | 93–99% | **39–43%** |
| 降到 5% 閾值可用 | 部分可用（3–7 lines） | **仍然 0 lines** |

### 4.3 降低閾值的效果

即使將閾值降到極低（v=5%, h=10%），**仍然 0 條格線**：

| 閾值 | R0 V/H | R1 V/H | R2 V/H |
|------|--------|--------|--------|
| v=0.18, h=0.22（現行） | 0/0 | 0/0 | 0/0 |
| v=0.10, h=0.15 | 0/0 | 0/0 | 0/0 |
| v=0.05, h=0.10 | 0/0 | 0/0 | 0/0 |

**結論：降低閾值完全無效。問題不在閾值，而在 morphological opening 本身。**

---

## 5. 根因分析

### 5.1 Morphological Opening 在大歪斜下徹底失效

debug 影像觀察（`tests/fixtures/debug_output/v_sample_r0_*.png`）：

| 步驟 | 結果 |
|------|------|
| Adaptive threshold | 格線和文字都清楚可見 |
| Vertical morphology | **幾乎全黑** — 垂直線完全被消除 |
| Horizontal morphology | **極度碎片化** — 只剩零星短段 |

### 5.2 數學解釋

Morphological opening 用 `(1, 26)` 的垂直 kernel，要求連續 26px 的嚴格垂直白點。

歪斜 θ=8° 時：
```
26px 垂直段的水平偏移 = 26 × tan(8°) ≈ 3.7 px
```

1px 寬的 kernel 完全無法容納 3.7px 的水平偏移 → **垂直線被完全消除**。

對比 fake_data_sample2.png（θ=4°）：
```
26px 段的偏移 = 26 × tan(4°) ≈ 1.8 px → 剛好在邊界，部分存活
```

| 歪斜角度 | 26px 段偏移 | Morphological 結果 | 投影達標率 |
|---------|-----------|-------------------|----------|
| 0° | 0 px | 完美保留 | 100% |
| 4° | 1.8 px | 部分存活 | 87–99% |
| **8°** | **3.7 px** | **完全消除** | **21–43%** |

### 5.3 這是根本性的方法限制

這不是參數調整問題。Morphological opening + axis-aligned projection 這個方法組合，在歪斜 ≥ 5° 時就開始嚴重劣化，≥ 8° 時完全不可用。

---

## 6. 自動旋轉機制評估

新版 `_detect_cells` 嘗試 4 個 rot_k（0°/90°/180°/270°），選 cell 數最多的方向。

| 面向 | 表現 | 評估 |
|------|------|------|
| 方向識別 | rot_k=1 正確找到 3 個記分區 | ✅ 有效 |
| 最佳方向選擇 | 因全部 0 cells，退化為選 rot_k=0 | ⚠️ 選擇正確但無意義 |
| 座標重映射 | `_remap_cells_to_original` 邏輯正確 | ✅ 有效 |

**自動旋轉解決了方向問題，但下游的格線偵測卡住，導致整體仍失敗。**

---

## 7. Pipeline 各階段狀態

```
v_sample.png (portrait, 8° skew)
  │
  ▼
[自動旋轉] 嘗試 4 個方向              ✅ rot_k=1 為最佳
  │
  ▼
[區域偵測] 找到 3/4 個記分區          ✅ 正確（第 4 個被裁切）
  │
  ▼
[格線偵測] morphological + projection  ❌ 全部 0 lines（8° 歪斜致命）
  │
  ▼
[Cell 組裝]                           ❌ 跳過
  │
  ▼
[文字放置]                            ❌ 跳過
```

---

## 8. 修正建議

### 核心結論：Deskew 是必要前置步驟

三個測試案例的結果清楚表明：

| 測試案例 | 歪斜 | 格線偵測 | 結論 |
|---------|------|---------|------|
| sample.png | 0° | ✅ 完美 | baseline |
| fake_data_sample2.png | 4° | ❌ 差一點點 | 閾值邊界 |
| **v_sample.png** | **8°** | **❌ 完全失敗** | **方法限制** |

### 建議修正方案

**在 `_detect_cells_for_orientation` 開頭加入 deskew：**

```python
def _detect_cells_for_orientation(self, arr: np.ndarray) -> list[list[Cell]]:
    arr = self._deskew(arr)  # ← 必須在格線偵測之前
    regions = self._detect_target_regions(arr)
    ...
```

deskew 的實作可直接複用 `image_quality._estimate_skew_angle()`：

```python
def _deskew(self, gray: np.ndarray) -> np.ndarray:
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
    if abs(median_angle) < 0.5:  # 不需校正
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w/2, h/2), median_angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)
```

### 修正後預期效果

| 測試案例 | 校正前歪斜 | 校正後歪斜 | 預期格線偵測 |
|---------|----------|----------|-----------|
| sample.png | 0° | 0°（不動） | ✅ 維持完美 |
| fake_data_sample2.png | 4° | ~0° | ✅ 應能偵測 |
| v_sample.png | 8° | ~0° | ✅ 應能偵測 |

---

## 9. 驗證方式

修正完成後，跑以下驗證：

```python
from PIL import Image
from score_reader.dataset.generator.sheet_renderer import SheetRenderer

renderer = SheetRenderer(seed=42)

# 1. 乾淨模板
cells = renderer._detect_cells(Image.open("sample.png").convert("RGB"))
assert len(cells) == 4 and all(len(c) >= 84 for c in cells), f"sample.png failed: {[len(c) for c in cells]}"

# 2. 帶 artifact 的 landscape 假資料
cells = renderer._detect_cells(Image.open("tests/fixtures/fake_data_sample2.png").convert("RGB"))
assert len(cells) >= 3 and all(len(c) >= 60 for c in cells), f"fake_data_sample2 failed: {[len(c) for c in cells]}"

# 3. 帶 artifact + 旋轉的 portrait 假資料（本報告對象）
cells = renderer._detect_cells(Image.open("tests/fixtures/v_sample.png").convert("RGB"))
assert len(cells) >= 3 and all(len(c) >= 60 for c in cells), f"v_sample failed: {[len(c) for c in cells]}"

print("All 3 test cases passed!")
```

---

## 10. 三份測試報告的統整結論

| 報告 | 影像 | 歪斜 | 區域偵測 | 格線偵測 | 卡點 |
|------|------|------|---------|---------|------|
| real_image_detection_analysis | real.png | -6° | ⚠️ 表頭誤判 | ❌ | 全域掃描 + 硬編碼 4 區 |
| fake_data_sample2_detection_analysis | fake_data_sample2.png | +4° | ✅ | ❌ | 投影閾值差一點 |
| **本報告** | **v_sample.png** | **-8°** | **✅** | **❌** | **morphological 完全失效** |

**三份報告指向同一個結論：需要在格線偵測之前加入 deskew 校正。**
這是目前 pipeline 的單一最大瓶頸，修正後三個測試案例預期都能通過。
