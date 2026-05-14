from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from score_reader.processing import ScoreSheetParser


class DebugVisualizer:
    _TARGET_COLORS = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 255, 255)]

    def __init__(self) -> None:
        self._parser = ScoreSheetParser()

    def generate(self, image_path: Path, output_dir: Path) -> list[Path]:
        _, artifacts = self._parser.parse_with_artifacts(image_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        step1 = artifacts.corrected_bgr.copy()
        self._draw_regions(step1, artifacts.target_regions)

        step2 = step1.copy()
        for rows in artifacts.target_rows:
            for row in rows:
                for cell in row:
                    cv2.rectangle(step2, (cell.left, cell.top), (cell.right, cell.bottom), (180, 180, 180), 1)

        step3 = step2.copy()
        for target_idx, arrow_cells in enumerate(artifacts.arrow_cells):
            color = self._TARGET_COLORS[target_idx % len(self._TARGET_COLORS)]
            for end_idx, arrow_idx, cell in arrow_cells:
                cv2.rectangle(step3, (cell.left, cell.top), (cell.right, cell.bottom), color, 2)
                cv2.putText(step3, f"E{end_idx}A{arrow_idx}", (cell.left + 2, cell.top + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)

        outputs = {
            "step1_corrected_regions.png": step1,
            "step2_cells.png": step2,
            "step3_arrow_cells.png": step3,
            "combined.png": step3,
        }
        written: list[Path] = []
        for name, canvas in outputs.items():
            path = output_dir / name
            cv2.imwrite(str(path), canvas)
            written.append(path)
        return written

    def _draw_regions(self, image: np.ndarray, regions: list[tuple[int, int, int, int]]) -> None:
        for i, (left, top, right, bottom) in enumerate(regions):
            color = self._TARGET_COLORS[i % len(self._TARGET_COLORS)]
            cv2.rectangle(image, (left, top), (right, bottom), color, 3)
            cv2.putText(image, f"Target {i+1}", (left + 5, max(16, top - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
