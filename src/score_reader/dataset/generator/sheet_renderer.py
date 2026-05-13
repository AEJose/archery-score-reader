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
        self._font_candidates = self._load_handwriting_fonts()

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

        stylized_layer = self._stylize_text_layer(text_layer)
        image = Image.alpha_composite(base.convert("RGBA"), stylized_layer).convert("RGB")
        image = self._apply_capture_artifacts(image)

        image.save(output_image)

    def _detect_cells(self, image: Image.Image) -> list[list[Cell]]:
        gray = image.convert("L")
        w, h = gray.size
        arr = np.array(gray)

        # Step 1: Find 4 scoring regions via OpenCV contours
        regions = self._detect_target_regions(arr)
        if len(regions) != 4:
            return []

        # Step 2: Find grid lines via dark-pixel scanning
        px = gray.load()

        dark_cols = []
        for x in range(w):
            dark_count = sum(1 for y in range(h) if px[x, y] < 130)
            if dark_count > h * 0.20:
                dark_cols.append(x)

        dark_rows = []
        for y in range(h):
            dark_count = sum(1 for x in range(w) if px[x, y] < 130)
            if dark_count > w * 0.20:
                dark_rows.append(y)

        v_lines = self._merge_lines(dark_cols)
        h_lines = self._merge_lines(dark_rows)
        if len(v_lines) < 8 or len(h_lines) < 8:
            return []

        # Step 3: Build cells per region (preserving region order for
        # correct alignment with _flatten_values)
        target_cells: list[list[Cell]] = []
        for left, top, right, bottom in regions:
            local_v = [x for x in v_lines if left <= x <= right]
            local_h = [y for y in h_lines if top <= y <= bottom]

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
        """Detect 4 athlete scoring regions using OpenCV contour detection.

        Uses cv2.findContours + cv2.approxPolyDP to find quadrilateral
        contours whose bounding-box area is close to 1/8 of the total
        image area.
        """
        img_h, img_w = gray.shape
        total_area = img_w * img_h
        target_area = total_area / 8
        area_lo = target_area * 0.5
        area_hi = target_area * 1.5

        _, binary = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        regions: list[tuple[int, int, int, int]] = []
        for cnt in contours:
            x, y, rw, rh = cv2.boundingRect(cnt)
            bbox_area = rw * rh
            if not (area_lo <= bbox_area <= area_hi):
                continue
            peri = cv2.arcLength(cnt, True)
            for eps_pct in (0.01, 0.02, 0.03, 0.05, 0.08):
                approx = cv2.approxPolyDP(cnt, eps_pct * peri, True)
                if len(approx) <= 6:
                    regions.append((x, y, x + rw, y + rh))
                    break

        regions.sort(key=lambda r: r[0])
        return regions[:4]

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

    def _create_writer_style(self) -> dict[str, object]:
        return {
            "size_scale": self._rng.uniform(0.92, 1.18),
            "size_boost": self._rng.uniform(1.0, 1.8),
            "stroke_shift": self._rng.randint(0, 1),
            "rotation": self._rng.uniform(-5.5, 5.5),
            "x_jitter": self._rng.uniform(-4.2, 4.2),
            "y_jitter": self._rng.uniform(-3.5, 3.5),
            "overflow_prob": self._rng.uniform(0.20, 0.45),
            "overflow_px": self._rng.uniform(0.5, 3.0),
            "ink": (self._rng.randint(18, 40), self._rng.randint(18, 40), self._rng.randint(18, 50), self._rng.randint(225, 255)),
            "font_path": self._rng.choice(self._font_candidates) if self._font_candidates else None,
        }

    def _pick_font(self, cell: Cell, writer_style: dict[str, object], value_len: int) -> ImageFont.ImageFont:
        cell_h = max(12, cell.bottom - cell.top)
        scale = float(writer_style["size_scale"])
        size_boost = float(writer_style["size_boost"])
        base_size = cell_h * 0.68 * scale
        target_size = max(11, int(base_size * 2.0 * size_boost))

        if self._rng.random() < float(writer_style["overflow_prob"]):
            target_size = int(target_size * self._rng.uniform(1.02, 1.10))
        font_path = writer_style.get("font_path")
        if isinstance(font_path, Path):
            try:
                return ImageFont.truetype(str(font_path), target_size)
            except OSError:
                pass
        return ImageFont.load_default()

    def _draw_cell_text(self, layer: Image.Image, cell: Cell, value: str, writer_style: dict[str, object]) -> None:
        draw = ImageDraw.Draw(layer)
        font = self._pick_font(cell, writer_style, len(value))
        bbox = draw.textbbox((0, 0), value, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = cell.left + (cell.right - cell.left - text_w) // 2 + int(float(writer_style["x_jitter"]))
        y = cell.top + (cell.bottom - cell.top - text_h) // 2 + int(float(writer_style["y_jitter"]))
        if self._rng.random() < float(writer_style["overflow_prob"]):
            overflow_px = float(writer_style["overflow_px"])
            x += int(self._rng.uniform(-overflow_px, overflow_px))
            y += int(self._rng.uniform(-overflow_px, overflow_px))
        ink = writer_style["ink"]

        if int(writer_style["stroke_shift"]) > 0:
            draw.text((x + 1, y), value, fill=(ink[0], ink[1], ink[2], max(120, ink[3] - 60)), font=font)
        draw.text((x, y), value, fill=ink, font=font)

    def _stylize_text_layer(self, text_layer: Image.Image) -> Image.Image:
        arr = np.array(text_layer)
        alpha = arr[:, :, 3]

        # Edge roughness and ink discontinuity
        k = 1
        kernel = np.ones((k, k), np.uint8)
        alpha = cv2.erode(alpha, kernel, iterations=1)
        alpha = cv2.dilate(alpha, kernel, iterations=1)

        noise = np.random.default_rng(self._rng.randint(1, 999999)).normal(0, 4.0, size=alpha.shape)
        alpha = np.clip(alpha.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        arr[:, :, 3] = alpha

        angle = self._rng.uniform(-0.25, 0.25)
        h, w = alpha.shape
        rot_m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(arr, rot_m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT)
        return Image.fromarray(rotated, mode="RGBA")

    def _apply_capture_artifacts(self, image: Image.Image) -> Image.Image:
        arr = np.array(image)
        h, w = arr.shape[:2]

        # Mild blur and lighting gradient to mimic camera capture
        if self._rng.random() < 0.65:
            sigma = self._rng.uniform(0.2, 0.45)
            arr = cv2.GaussianBlur(arr, (3, 3), sigmaX=sigma)

        gradient = np.linspace(self._rng.uniform(0.97, 1.0), self._rng.uniform(1.0, 1.03), w, dtype=np.float32)
        grad_map = np.tile(gradient, (h, 1))[:, :, None]
        arr = np.clip(arr.astype(np.float32) * grad_map, 0, 255).astype(np.uint8)

        # JPEG-like compression artifacts
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self._rng.randint(86, 95)]
        ok, enc = cv2.imencode(".jpg", cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), encode_param)
        if ok:
            dec = cv2.imdecode(enc, cv2.IMREAD_COLOR)
            arr = cv2.cvtColor(dec, cv2.COLOR_BGR2RGB)

        return Image.fromarray(arr)
