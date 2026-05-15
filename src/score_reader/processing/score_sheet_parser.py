import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from score_reader.dataset.generator.sheet_renderer import Cell, SheetRenderer
from score_reader.recognition.models import ArrowReading, EndReading, StructuredScoreSheet, TargetReading
from score_reader.recognition.ocr_engine import OCREngine

_VALID = {"X", "M", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "0"}


@dataclass
class PipelineArtifacts:
    corrected_bgr: np.ndarray
    target_regions: list[tuple[int, int, int, int]]
    target_rows: list[list[list[Cell]]]
    arrow_cells: list[list[tuple[int, int, Cell]]]
    score_tables: list[tuple[int, int, int, int]]


@dataclass
class CardProcessingResult:
    rows: list[list[Cell]]
    arrow_cells: list[tuple[int, int, Cell]]
    arrows: list[ArrowReading]
    score_table_bbox: tuple[int, int, int, int]


class CardRegionProcessor:
    def __init__(self, renderer: SheetRenderer, ocr_engine: OCREngine) -> None:
        self._renderer = renderer
        self._ocr_engine = ocr_engine

    def process(self, gray: np.ndarray, region: tuple[int, int, int, int]) -> CardProcessingResult:
        left, top, right, bottom = region
        card_gray = gray[top:bottom, left:right]
        card_gray = self._normalize_card_orientation(card_gray)
        table_l, table_t, table_r, table_b = self._detect_score_table_bbox(card_gray)
        cells = self._detect_cells(card_gray, table_l, table_t, table_r, table_b)
        rows = self._renderer._group_cells_by_rows(cells)
        arrow_cells = self._classify_arrow_cells(rows)
        arrows = self._read_arrows(card_gray, arrow_cells)
        return CardProcessingResult(
            rows=rows,
            arrow_cells=arrow_cells,
            arrows=arrows,
            score_table_bbox=(left + table_l, top + table_t, left + table_r, top + table_b),
        )

    def _read_arrows(self, card_gray: np.ndarray, arrow_cells: list[tuple[int, int, Cell]]) -> list[ArrowReading]:
        card_bgr = cv2.cvtColor(card_gray, cv2.COLOR_GRAY2BGR)
        arrows: list[ArrowReading] = []
        for end_idx, arrow_idx, cell in arrow_cells:
            crop = self._crop_cell(card_bgr, cell, 2)
            value, conf = self._ocr_cell(crop)
            arrows.append(ArrowReading(arrow_index=(end_idx - 1) * 6 + arrow_idx, value=value, confidence=conf))
        return arrows

    def _normalize_card_orientation(self, card_gray: np.ndarray) -> np.ndarray:
        best = card_gray
        best_score = -1.0
        for k in (0, 1, 2, 3):
            candidate = np.rot90(card_gray, k=k).copy()
            h, w = candidate.shape
            if h < 50 or w < 50:
                continue
            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, h // 24)))
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, w // 18), 1))
            binary = cv2.adaptiveThreshold(candidate, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 5)
            vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
            horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
            score = float(vertical.sum() + horizontal.sum())
            if score > best_score:
                best = candidate
                best_score = score
        return best

    def _detect_score_table_bbox(self, card_gray: np.ndarray) -> tuple[int, int, int, int]:
        h, w = card_gray.shape
        binary = cv2.adaptiveThreshold(card_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 5)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, h // 24)))
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, w // 18), 1))
        vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
        grid = cv2.bitwise_or(vertical, horizontal)
        contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return int(w * 0.12), int(h * 0.2), int(w * 0.96), int(h * 0.88)
        x, y, cw, ch = max((cv2.boundingRect(c) for c in contours), key=lambda b: b[2] * b[3])
        pad_x = max(4, cw // 40)
        pad_y = max(4, ch // 40)
        return max(0, x - pad_x), max(0, y - pad_y), min(w, x + cw + pad_x), min(h, y + ch + pad_y)

    def _detect_cells(self, gray: np.ndarray, left: int, top: int, right: int, bottom: int) -> list[Cell]:
        local_v, local_h = self._renderer._detect_region_grid_lines(gray, left, top, right, bottom)
        if len(local_v) < 5 or len(local_h) < 10:
            local_v, local_h = self._fallback_detect_lines(gray, left, top, right, bottom)
        cells: list[Cell] = []
        for r1, r2 in zip(local_h, local_h[1:]):
            for c1, c2 in zip(local_v, local_v[1:]):
                if r2 - r1 < 12 or c2 - c1 < 12:
                    continue
                cells.append(Cell(c1 + 2, r1 + 2, c2 - 2, r2 - 2))
        return cells

    def _fallback_detect_lines(self, gray: np.ndarray, left: int, top: int, right: int, bottom: int) -> tuple[list[int], list[int]]:
        region = gray[top:bottom, left:right]
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(region)
        merged = np.zeros_like(region)
        for block, c in ((15, 3), (21, 6), (31, 9)):
            b = cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, c)
            merged = cv2.bitwise_or(merged, b)
        h, w = region.shape
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, h // 20)))
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, w // 16), 1))
        vertical = cv2.morphologyEx(merged, cv2.MORPH_OPEN, v_kernel)
        horizontal = cv2.morphologyEx(merged, cv2.MORPH_OPEN, h_kernel)
        v_proj = vertical.sum(axis=0) / 255
        h_proj = horizontal.sum(axis=1) / 255
        v_candidates = np.where(v_proj > h * 0.12)[0].tolist()
        h_candidates = np.where(h_proj > w * 0.15)[0].tolist()
        local_v = [left + x for x in self._renderer._merge_lines(v_candidates)]
        local_h = [top + y for y in self._renderer._merge_lines(h_candidates)]
        return local_v, local_h

    def _classify_arrow_cells(self, rows: list[list[Cell]]) -> list[tuple[int, int, Cell]]:
        scoring_rows = [row for row in rows if len(row) >= 6]
        if len(scoring_rows) > 12:
            scoring_rows = scoring_rows[:12]
        elif len(scoring_rows) < 12:
            return []
        out: list[tuple[int, int, Cell]] = []
        for end_idx in range(6):
            row_a = scoring_rows[end_idx * 2]
            row_b = scoring_rows[end_idx * 2 + 1]
            for i in range(3):
                out.append((end_idx + 1, i + 1, row_a[i]))
                out.append((end_idx + 1, i + 4, row_b[i]))
        return out

    def _crop_cell(self, image: np.ndarray, cell: Cell, pad: int) -> np.ndarray:
        h, w = image.shape[:2]
        l, t = max(0, cell.left - pad), max(0, cell.top - pad)
        r, b = min(w, cell.right + pad), min(h, cell.bottom + pad)
        return image[t:b, l:r]

    def _ocr_cell(self, crop: np.ndarray) -> tuple[str, float]:
        if crop.size == 0:
            return "M", 0.0
        tokens = self._ocr_engine.run_array(crop)
        best_val, best_conf = "M", 0.0
        for token in tokens:
            normalized = _normalize_token(token.text)
            if normalized is None:
                continue
            if token.confidence >= best_conf:
                best_val, best_conf = normalized, token.confidence
        return best_val, best_conf


def _normalize_token(token: str) -> str | None:
    text = token.strip().replace("×", "X").replace("x", "X").replace("o", "0").replace("O", "0")
    text = text.rstrip(".,;:，。")
    cleaned = re.sub(r"[^0-9XxMm]", "", text)
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in _VALID:
        return upper
    if len(upper) > 1:
        if "10" in upper:
            return "10"
        for ch in upper:
            if ch in {"X", "M", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
                return ch
    return None


def _to_score(value: str) -> int:
    if value in {"X", "10"}:
        return 10
    if value == "M":
        return 0
    return int(value)


class ScoreSheetParser:
    def __init__(self, ocr_engine: OCREngine | None = None) -> None:
        self.ocr_engine = ocr_engine or OCREngine()
        self._renderer = SheetRenderer()
        self._card_processor = CardRegionProcessor(self._renderer, self.ocr_engine)

    def parse(self, image_path: Path) -> StructuredScoreSheet:
        parsed, _ = self.parse_with_artifacts(image_path)
        return parsed

    def parse_with_artifacts(self, image_path: Path) -> tuple[StructuredScoreSheet, PipelineArtifacts]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")

        corrected = self._correct_image(image)
        gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
        regions = self._renderer._detect_target_regions(gray)

        target_rows: list[list[list[Cell]]] = []
        target_arrow_cells: list[list[tuple[int, int, Cell]]] = []
        score_tables: list[tuple[int, int, int, int]] = []
        targets: list[TargetReading] = []

        for target_idx, (left, top, right, bottom) in enumerate(regions[:4], start=1):
            card_result = self._card_processor.process(gray, (left, top, right, bottom))
            rows = card_result.rows
            arrow_cells = card_result.arrow_cells
            arrows = card_result.arrows
            score_tables.append(card_result.score_table_bbox)

            ends: list[EndReading] = []
            for end_idx in range(1, 7):
                end_arrows = [a for a in arrows if (a.arrow_index - 1) // 6 + 1 == end_idx]
                end_arrows.sort(key=lambda a: a.arrow_index)
                subtotal = sum(_to_score(a.value) for a in end_arrows)
                ends.append(EndReading(end_index=end_idx, arrows=end_arrows, subtotal=subtotal))

            total = sum(e.subtotal for e in ends)
            targets.append(TargetReading(target_index=target_idx, arrows=arrows, ends=ends, total=total))
            target_rows.append(rows)
            target_arrow_cells.append(arrow_cells)

        # pad targets to 4 for compatible schema
        while len(targets) < 4:
            idx = len(targets) + 1
            targets.append(TargetReading(target_index=idx, arrows=[], ends=[EndReading(end_index=i) for i in range(1, 7)], total=0))

        result = StructuredScoreSheet(image_path=str(image_path), targets=targets, raw_tokens=[])
        artifacts = PipelineArtifacts(corrected, regions[:4], target_rows, target_arrow_cells, score_tables)
        return result, artifacts

    def _correct_image(self, image: np.ndarray) -> np.ndarray:
        best_img = image
        best_regions: list[tuple[int, int, int, int]] = []
        for rot_k in (0, 1, 2, 3):
            candidate = np.rot90(image, k=rot_k).copy()
            gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
            gray = self._renderer._deskew(gray)
            candidate = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            candidate = self._perspective_warp(candidate)
            regions = self._renderer._detect_target_regions(cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY))
            if len(regions) > len(best_regions):
                best_regions = regions
                best_img = candidate
        return best_img

    def _perspective_warp(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 180)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:8]
        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) != 4:
                continue
            pts = approx.reshape(4, 2).astype(np.float32)
            rect = self._order_points(pts)
            (tl, tr, br, bl) = rect
            max_w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            max_h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
            if max_w < 300 or max_h < 300:
                continue
            dst = np.array([[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]], dtype=np.float32)
            m = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(image, m, (max_w, max_h))
            return warped
        return image

    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1)
        return np.array([pts[np.argmin(s)], pts[np.argmin(diff)], pts[np.argmax(s)], pts[np.argmax(diff)]], dtype=np.float32)
