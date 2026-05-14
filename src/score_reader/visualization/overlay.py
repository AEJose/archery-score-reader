from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from score_reader.dataset.generator.sheet_renderer import SheetRenderer
from score_reader.recognition import OCREngine


class DebugVisualizer:
    """Generate debug overlay images for score-sheet detection and OCR."""

    _TARGET_COLORS = [
        (0, 0, 255),
        (0, 200, 0),
        (255, 0, 0),
        (0, 255, 255),
    ]

    def __init__(self) -> None:
        self._renderer = SheetRenderer()
        self._ocr = OCREngine()

    def generate(self, image_path: Path, output_dir: Path) -> list[Path]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        regions = self._renderer._detect_target_regions(gray)
        step1 = image.copy()
        self._draw_regions(step1, regions)

        step2 = step1.copy()
        for left, top, right, bottom in regions:
            cells = self._detect_cells(gray, left, top, right, bottom)
            self._draw_cells(step2, cells)

        step3 = step2.copy()
        tokens = self._ocr.run(image_path)
        self._draw_tokens(step3, tokens)

        outputs = {
            "step1_target_regions.png": step1,
            "step2_cells.png": step2,
            "step3_ocr_results.png": step3,
            "combined.png": step3,
        }

        written: list[Path] = []
        for filename, canvas in outputs.items():
            out_path = output_dir / filename
            cv2.imwrite(str(out_path), canvas)
            written.append(out_path)
        return written

    def _detect_cells(self, gray: np.ndarray, left: int, top: int, right: int, bottom: int):
        local_v, local_h = self._renderer._detect_region_grid_lines(gray, left, top, right, bottom)
        cells = []
        for r1, r2 in zip(local_h, local_h[1:]):
            for c1, c2 in zip(local_v, local_v[1:]):
                if r2 - r1 < 14 or c2 - c1 < 14:
                    continue
                cells.append((c1 + 2, r1 + 2, c2 - 2, r2 - 2))
        return cells

    def _draw_regions(self, image: np.ndarray, regions: list[tuple[int, int, int, int]]) -> None:
        for i, (left, top, right, bottom) in enumerate(regions):
            color = self._TARGET_COLORS[i % len(self._TARGET_COLORS)]
            cv2.rectangle(image, (left, top), (right, bottom), color, 3)
            cv2.putText(
                image,
                f"Target {i + 1}",
                (left + 4, max(16, top - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

    def _draw_cells(self, image: np.ndarray, cells: list[tuple[int, int, int, int]]) -> None:
        overlay = image.copy()
        for left, top, right, bottom in cells:
            cv2.rectangle(overlay, (left, top), (right, bottom), (180, 180, 180), 1)
        cv2.addWeighted(overlay, 0.6, image, 0.4, 0, image)

    def _draw_tokens(self, image: np.ndarray, tokens) -> None:
        for token in tokens:
            left, top, width, height = token.bbox
            right, bottom = left + width, top + height
            cv2.rectangle(image, (left, top), (right, bottom), (255, 255, 255), 1)

            confidence_pct = int(round(token.confidence * 100))
            label = f"{token.text} {confidence_pct}%"
            bg_color = self._confidence_color(token.confidence)
            self._draw_label(image, label, left, max(0, top - 18), bg_color)

    def _draw_label(self, image: np.ndarray, text: str, x: int, y: int, bg_color: tuple[int, int, int]) -> None:
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.43, 1)
        pad = 3
        x1, y1 = x, y
        x2, y2 = x + text_w + pad * 2, y + text_h + baseline + pad * 2
        x2 = min(x2, image.shape[1] - 1)
        y2 = min(y2, image.shape[0] - 1)

        overlay = image.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), bg_color, -1)
        cv2.addWeighted(overlay, 0.45, image, 0.55, 0, image)
        cv2.putText(
            image,
            text,
            (x1 + pad, y1 + text_h + pad),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )

    def _confidence_color(self, conf: float) -> tuple[int, int, int]:
        if conf >= 0.8:
            return (0, 220, 0)
        if conf >= 0.5:
            return (0, 220, 220)
        return (0, 0, 220)
