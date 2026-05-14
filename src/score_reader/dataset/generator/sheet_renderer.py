from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from score_reader.dataset.models import SyntheticTarget


@dataclass
class Cell:
    left: int
    top: int
    right: int
    bottom: int


class SheetRenderer:
    """Render synthetic scores into the score-sheet template."""

    def __init__(self, seed: int = 20260513) -> None:
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)
        self._font_candidates = self._load_handwriting_fonts()
        self._fallback_font = self._find_fallback_font()

    def render(self, template_image: Path, output_image: Path, targets: list[SyntheticTarget]) -> None:
        image = Image.open(template_image).convert("RGB")
        base = image.copy()

        per_target_cells = self._detect_cells(image)
        if not per_target_cells:
            image.save(output_image)
            return

        text_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        for target, cells in zip(targets, per_target_cells):
            placement = self._build_target_placement(cells, target)
            writer_style = self._create_writer_style()
            for cell, value in placement:
                self._draw_cell_text(text_layer, cell, value, writer_style)

        image = Image.alpha_composite(base.convert("RGBA"), text_layer).convert("RGB")
        image = self._apply_capture_artifacts(image)
        image = self._apply_orientation_variant(image)

        image.save(output_image)

    def _apply_orientation_variant(self, image: Image.Image) -> Image.Image:
        """Augment orientation to include rotated and upside-down sheets."""
        angle = self._rng.choice((0, 90, 180, 270))
        if angle == 0:
            return image
        return image.rotate(angle, expand=True, fillcolor=(255, 255, 255))

    def _detect_cells(self, image: Image.Image) -> list[list[Cell]]:
        gray = image.convert("L")
        base_arr = np.array(gray)
        base_h, base_w = base_arr.shape

        best_cells: list[list[Cell]] = []
        best_score = -1
        for rot_k in (0, 1, 2, 3):
            arr = np.rot90(base_arr, k=rot_k)
            rotated_cells = self._detect_cells_for_orientation(arr)
            recovered = self._remap_cells_to_original(rotated_cells, base_w, base_h, rot_k)
            score = sum(len(cells) for cells in recovered)
            if score > best_score:
                best_score = score
                best_cells = recovered

        return best_cells

    def _detect_cells_for_orientation(self, arr: np.ndarray) -> list[list[Cell]]:
        arr = self._deskew(arr)
        regions = self._detect_target_regions(arr)
        if not regions:
            return []

        target_cells: list[list[Cell]] = []
        for left, top, right, bottom in regions:
            local_v, local_h = self._detect_region_grid_lines(arr, left, top, right, bottom)
            if len(local_v) < 4 or len(local_h) < 8:
                continue

            region_cells: list[Cell] = []
            for r1, r2 in zip(local_h, local_h[1:]):
                row_h = r2 - r1
                if row_h < 22 or row_h > 110:
                    continue
                for c1, c2 in zip(local_v, local_v[1:]):
                    col_w = c2 - c1
                    if col_w < 24 or col_w > 170:
                        continue
                    region_cells.append(Cell(c1 + 3, r1 + 3, c2 - 3, r2 - 3))

            region_cells.sort(key=lambda c: (c.top, c.left))
            target_cells.append(region_cells)

        return target_cells

    def _remap_cells_to_original(self, cells_by_target: list[list[Cell]], base_w: int, base_h: int, rot_k: int) -> list[list[Cell]]:
        if rot_k == 0:
            return cells_by_target

        remapped: list[list[Cell]] = []
        for target_cells in cells_by_target:
            mapped_cells = [self._remap_cell_to_original(cell, base_w, base_h, rot_k) for cell in target_cells]
            mapped_cells.sort(key=lambda c: (c.top, c.left))
            remapped.append(mapped_cells)
        remapped.sort(key=lambda cells: min((cell.left for cell in cells), default=10**9))
        return remapped

    def _remap_cell_to_original(self, cell: Cell, base_w: int, base_h: int, rot_k: int) -> Cell:
        points = (
            (cell.left, cell.top),
            (cell.right, cell.top),
            (cell.right, cell.bottom),
            (cell.left, cell.bottom),
        )

        mapped = [self._map_point_to_original(x, y, base_w, base_h, rot_k) for x, y in points]
        xs = [p[0] for p in mapped]
        ys = [p[1] for p in mapped]
        return Cell(min(xs), min(ys), max(xs), max(ys))

    def _map_point_to_original(self, x: int, y: int, base_w: int, base_h: int, rot_k: int) -> tuple[int, int]:
        if rot_k == 1:
            return y, base_h - 1 - x
        if rot_k == 2:
            return base_w - 1 - x, base_h - 1 - y
        if rot_k == 3:
            return base_w - 1 - y, x
        return x, y

    def _detect_region_grid_lines(
        self,
        gray: np.ndarray,
        left: int,
        top: int,
        right: int,
        bottom: int,
    ) -> tuple[list[int], list[int]]:
        region = gray[top:bottom, left:right]
        if region.size == 0:
            return [], []

        binary = cv2.adaptiveThreshold(
            region,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            21,
            7,
        )

        h, w = region.shape
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(12, h // 16)))
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 12), 1))
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)

        v_proj = vertical.sum(axis=0) / 255
        h_proj = horizontal.sum(axis=1) / 255

        v_candidates = np.where(v_proj > h * 0.18)[0].tolist()
        h_candidates = np.where(h_proj > w * 0.22)[0].tolist()

        local_v = [left + x for x in self._merge_lines(v_candidates)]
        local_h = [top + y for y in self._merge_lines(h_candidates)]
        return local_v, local_h

    def _deskew(self, gray: np.ndarray) -> np.ndarray:
        edges = cv2.Canny(gray, 80, 180)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 120, minLineLength=80, maxLineGap=12)
        if lines is None:
            return gray

        angles: list[float] = []
        for line in lines[:, 0]:
            x1, y1, x2, y2 = line
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if -45.0 <= angle <= 45.0:
                angles.append(angle)

        if not angles:
            return gray

        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.3:
            return gray

        h, w = gray.shape
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), median_angle, 1.0)
        return cv2.warpAffine(
            gray,
            matrix,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _build_target_placement(self, cells: list[Cell], target: SyntheticTarget) -> list[tuple[Cell, str]]:
        rows = self._group_cells_by_rows(cells)
        if len(rows) < 12:
            return []

        scoring_rows = rows[:12]
        placements: list[tuple[Cell, str]] = []

        for end_idx, end in enumerate(target.rounds):
            row_a = scoring_rows[end_idx * 2]
            row_b = scoring_rows[end_idx * 2 + 1]
            if len(row_a) < 6 or len(row_b) < 6:
                continue

            # 每列：3 支箭 + 列小計；每兩列右兩欄代表該輪小計與累計。
            first_three = end.arrows[:3]
            last_three = end.arrows[3:]
            row_a_sum = sum(a.score_value for a in first_three)
            row_b_sum = sum(a.score_value for a in last_three)

            for i, arrow in enumerate(first_three):
                placements.append((row_a[i], arrow.value))
            placements.append((row_a[3], str(row_a_sum)))

            for i, arrow in enumerate(last_three):
                placements.append((row_b[i], arrow.value))
            placements.append((row_b[3], str(row_b_sum)))

            placements.append((row_a[4], str(end.subtotal)))
            placements.append((row_a[5], str(end.cumulative)))

        return placements

    def _group_cells_by_rows(self, cells: list[Cell]) -> list[list[Cell]]:
        if not cells:
            return []
        cells_sorted = sorted(cells, key=lambda c: (c.top, c.left))
        buckets: dict[int, list[Cell]] = defaultdict(list)
        row_keys: list[int] = []
        for cell in cells_sorted:
            assigned_key = None
            for key in row_keys:
                if abs(cell.top - key) <= 8:
                    assigned_key = key
                    break
            if assigned_key is None:
                assigned_key = cell.top
                row_keys.append(assigned_key)
            buckets[assigned_key].append(cell)

        rows = [sorted(buckets[key], key=lambda c: c.left) for key in sorted(row_keys)]
        return rows

    def _detect_target_regions(self, gray: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Detect scoring regions using contour and geometry filtering."""
        img_h, img_w = gray.shape
        total_area = img_w * img_h
        area_lo = total_area * 0.04
        area_hi = total_area * 0.24

        _, binary = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions: list[tuple[int, int, int, int]] = []
        for cnt in contours:
            x, y, rw, rh = cv2.boundingRect(cnt)
            bbox_area = rw * rh
            if not (area_lo <= bbox_area <= area_hi):
                continue
            aspect = rh / max(rw, 1)
            if aspect < 1.1:
                continue
            fill_ratio = cv2.contourArea(cnt) / max(float(bbox_area), 1.0)
            if fill_ratio < 0.45:
                continue
            regions.append((x, y, x + rw, y + rh))

        regions = self._dedupe_regions(regions)
        regions.sort(key=lambda r: r[0])
        return regions[:4]

    def _dedupe_regions(self, regions: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
        if not regions:
            return []
        regions = sorted(regions, key=lambda r: (r[0], r[1], -(r[2] - r[0]) * (r[3] - r[1])))
        kept: list[tuple[int, int, int, int]] = []
        for cand in regions:
            cx1, cy1, cx2, cy2 = cand
            c_area = (cx2 - cx1) * (cy2 - cy1)
            dup = False
            for kx1, ky1, kx2, ky2 in kept:
                ix1, iy1 = max(cx1, kx1), max(cy1, ky1)
                ix2, iy2 = min(cx2, kx2), min(cy2, ky2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                inter = (ix2 - ix1) * (iy2 - iy1)
                k_area = (kx2 - kx1) * (ky2 - ky1)
                if inter / max(min(c_area, k_area), 1) > 0.75:
                    dup = True
                    break
            if not dup:
                kept.append(cand)
        return kept

    def _merge_lines(self, indices: list[int]) -> list[int]:
        if not indices:
            return []
        groups: list[list[int]] = [[indices[0]]]
        for idx in indices[1:]:
            if idx - groups[-1][-1] <= 2:
                groups[-1].append(idx)
            else:
                groups.append([idx])
        return [sum(g) // len(g) for g in groups]


    def _apply_capture_artifacts(self, image: Image.Image) -> Image.Image:
        arr = np.array(image.convert("RGB"), dtype=np.uint8)

        # 手持拍攝常見：輕微旋轉 + 透視偏移（不翻轉）
        arr = self._apply_affine_jitter(arr)
        arr = self._apply_perspective_jitter(arr)

        # 不同曝光/陰影/噪點
        arr = self._apply_exposure_and_shadows(arr)
        arr = self._apply_sensor_noise(arr)

        return Image.fromarray(arr, mode="RGB")

    def _apply_affine_jitter(self, arr: np.ndarray) -> np.ndarray:
        h, w = arr.shape[:2]
        angle = self._rng.uniform(-7.0, 7.0)
        scale = self._rng.uniform(0.97, 1.03)
        tx = self._rng.uniform(-0.025 * w, 0.025 * w)
        ty = self._rng.uniform(-0.02 * h, 0.02 * h)
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, scale)
        matrix[0, 2] += tx
        matrix[1, 2] += ty
        return cv2.warpAffine(arr, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def _apply_perspective_jitter(self, arr: np.ndarray) -> np.ndarray:
        h, w = arr.shape[:2]
        margin = min(w, h) * self._rng.uniform(0.015, 0.045)

        src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
        dst = np.float32([
            [self._rng.uniform(0, margin), self._rng.uniform(0, margin)],
            [w - 1 - self._rng.uniform(0, margin), self._rng.uniform(0, margin)],
            [w - 1 - self._rng.uniform(0, margin), h - 1 - self._rng.uniform(0, margin)],
            [self._rng.uniform(0, margin), h - 1 - self._rng.uniform(0, margin)],
        ])
        matrix = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(arr, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def _apply_exposure_and_shadows(self, arr: np.ndarray) -> np.ndarray:
        arr_f = arr.astype(np.float32)

        alpha = self._rng.uniform(0.86, 1.18)
        beta = self._rng.uniform(-26.0, 24.0)
        arr_f = arr_f * alpha + beta

        h, w = arr.shape[:2]
        if self._rng.random() < 0.9:
            x = np.linspace(-1.0, 1.0, w, dtype=np.float32)
            y = np.linspace(-1.0, 1.0, h, dtype=np.float32)
            xx, yy = np.meshgrid(x, y)
            angle = self._rng.uniform(0.0, np.pi)
            grad = np.cos(angle) * xx + np.sin(angle) * yy
            grad = (grad - grad.min()) / (grad.max() - grad.min() + 1e-6)
            strength = self._rng.uniform(0.72, 1.15)
            shade = (0.8 + 0.2 * grad) * strength
            arr_f *= shade[..., None]

        return np.clip(arr_f, 0, 255).astype(np.uint8)

    def _apply_sensor_noise(self, arr: np.ndarray) -> np.ndarray:
        arr_f = arr.astype(np.float32)

        gaussian_sigma = self._rng.uniform(2.0, 9.0)
        gaussian = self._np_rng.normal(0.0, gaussian_sigma, arr.shape).astype(np.float32)
        arr_f += gaussian

        if self._rng.random() < 0.7:
            blurred = cv2.GaussianBlur(arr_f, (0, 0), sigmaX=self._rng.uniform(0.2, 1.2))
            blend = self._rng.uniform(0.08, 0.25)
            arr_f = arr_f * (1 - blend) + blurred * blend

        return np.clip(arr_f, 0, 255).astype(np.uint8)

    def _load_handwriting_fonts(self) -> list[Path]:
        search_roots = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
        ]
        tokens = (
            "hand",
            "script",
            "cursive",
            "comic",
            "chalk",
            "brush",
            "marker",
            "patrick",
            "indie",
            "architect",
            "caveat",
        )
        matches: list[Path] = []
        for root in search_roots:
            if not root.exists():
                continue
            for path in root.rglob("*.ttf"):
                name = path.name.lower()
                if any(token in name for token in tokens):
                    matches.append(path)
            for path in root.rglob("*.otf"):
                name = path.name.lower()
                if any(token in name for token in tokens):
                    matches.append(path)
        return matches


    def _find_fallback_font(self) -> Path | None:
        fallback_names = (
            "DejaVuSans.ttf",
            "DejaVuSerif.ttf",
            "NotoSansCJK-Regular.ttc",
            "NotoSansCJKtc-Regular.otf",
            "Arial.ttf",
        )
        search_roots = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
        for root in search_roots:
            if not root.exists():
                continue
            for name in fallback_names:
                matches = list(root.rglob(name))
                if matches:
                    return matches[0]
        return None

    def _create_writer_style(self) -> dict[str, object]:
        return {
            "size_scale": self._rng.uniform(0.92, 1.18),
            "size_boost": self._rng.uniform(1.0, 1.4),
            "rotation": self._rng.uniform(-8.0, 8.0),
            "x_jitter": self._rng.uniform(-4.2, 4.2),
            "y_jitter": self._rng.uniform(-3.5, 3.5),
            "overflow_prob": self._rng.uniform(0.20, 0.45),
            "overflow_px": self._rng.uniform(0.8, 3.2),
            "ink": (self._rng.randint(18, 40), self._rng.randint(18, 40), self._rng.randint(18, 50), self._rng.randint(225, 255)),
            "font_path": self._rng.choice(self._font_candidates) if self._font_candidates else None,
        }

    def _pick_font(self, cell: Cell, writer_style: dict[str, object], value_len: int) -> ImageFont.ImageFont:
        cell_h = max(12, cell.bottom - cell.top)
        scale = float(writer_style["size_scale"])
        size_boost = float(writer_style["size_boost"])
        base_size = cell_h * 0.68 * scale
        target_size = max(11, int(base_size * size_boost))

        if self._rng.random() < float(writer_style["overflow_prob"]):
            target_size = int(target_size * self._rng.uniform(1.03, 1.12))

        preferred = writer_style.get("font_path")
        candidate_paths: list[Path] = []
        if isinstance(preferred, Path):
            candidate_paths.append(preferred)
        if self._fallback_font is not None:
            candidate_paths.append(self._fallback_font)

        for font_path in candidate_paths:
            try:
                return ImageFont.truetype(str(font_path), target_size)
            except OSError:
                continue

        return ImageFont.load_default()

    def _draw_cell_text(self, layer: Image.Image, cell: Cell, value: str, writer_style: dict[str, object]) -> None:
        font = self._pick_font(cell, writer_style, len(value))
        probe_draw = ImageDraw.Draw(layer)
        bbox = probe_draw.textbbox((0, 0), value, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = cell.left + (cell.right - cell.left - text_w) // 2 + int(float(writer_style["x_jitter"]))
        y = cell.top + (cell.bottom - cell.top - text_h) // 2 + int(float(writer_style["y_jitter"]))
        if self._rng.random() < float(writer_style["overflow_prob"]):
            overflow_px = float(writer_style["overflow_px"])
            x += int(self._rng.uniform(-overflow_px, overflow_px))
            y += int(self._rng.uniform(-overflow_px, overflow_px))
        ink = writer_style["ink"]
        text_patch = Image.new("RGBA", (text_w + 24, text_h + 24), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_patch)
        text_draw.text((12, 12), value, fill=ink, font=font)
        rotated_patch = text_patch.rotate(float(writer_style["rotation"]), resample=Image.Resampling.BICUBIC, expand=True)
        layer.alpha_composite(rotated_patch, (x - 12, y - 12))
