from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

    def render(self, template_image: Path, output_image: Path, targets: list[SyntheticTarget]) -> None:
        image = Image.open(template_image).convert("RGB")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        cells = self._detect_cells(image)
        if not cells:
            image.save(output_image)
            return

        text_values = self._flatten_values(targets)
        for cell, value in zip(cells, text_values):
            self._draw_cell_text(draw, cell, value, font)

        image.save(output_image)

    def _detect_cells(self, image: Image.Image) -> list[Cell]:
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
        cells: list[Cell] = []
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
            cells.extend(region_cells)

        return cells

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

    def _flatten_values(self, targets: list[SyntheticTarget]) -> list[str]:
        values: list[str] = []
        for target in targets:
            for end in target.rounds:
                for arrow in end.arrows:
                    values.append(arrow.value)
                values.append(str(end.subtotal))
                values.append(str(end.cumulative))
            values.extend([str(target.x_count), str(target.x_plus_ten_count), str(target.total)])
        return values

    def _draw_cell_text(self, draw: ImageDraw.ImageDraw, cell: Cell, value: str, font: ImageFont.ImageFont) -> None:
        bbox = draw.textbbox((0, 0), value, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = cell.left + (cell.right - cell.left - text_w) // 2
        y = cell.top + (cell.bottom - cell.top - text_h) // 2
        draw.text((x, y), value, fill=(10, 10, 10), font=font)
