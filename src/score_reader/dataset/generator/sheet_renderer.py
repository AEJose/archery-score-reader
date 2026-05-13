from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
        px = gray.load()

        dark_cols = []
        for x in range(w):
            dark_count = sum(1 for y in range(h) if px[x, y] < 110)
            if dark_count > h * 0.30:
                dark_cols.append(x)

        dark_rows = []
        for y in range(h):
            dark_count = sum(1 for x in range(w) if px[x, y] < 110)
            if dark_count > w * 0.30:
                dark_rows.append(y)

        v_lines = self._merge_lines(dark_cols)
        h_lines = self._merge_lines(dark_rows)
        if len(v_lines) < 8 or len(h_lines) < 12:
            return []

        cells: list[Cell] = []
        for r1, r2 in zip(h_lines, h_lines[1:]):
            row_h = r2 - r1
            if row_h < 24 or row_h > 95:
                continue
            for c1, c2 in zip(v_lines, v_lines[1:]):
                col_w = c2 - c1
                if col_w < 26 or col_w > 140:
                    continue
                cells.append(Cell(c1 + 3, r1 + 3, c2 - 3, r2 - 3))

        cells.sort(key=lambda c: (c.top, c.left))
        return cells

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
