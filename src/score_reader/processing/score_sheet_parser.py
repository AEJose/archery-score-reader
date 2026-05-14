import re
from pathlib import Path

from score_reader.recognition.models import ArrowReading, EndReading, StructuredScoreSheet, TargetReading
from score_reader.recognition.ocr_engine import OCREngine

_VALID = {"X", "M", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "0"}


def _normalize_token(token: str) -> str | None:
    cleaned = re.sub(r"[^0-9xXmM]", "", token)
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in _VALID:
        return upper
    if upper == "O":
        return "0"
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

    def parse(self, image_path: Path) -> StructuredScoreSheet:
        tokens = self.ocr_engine.run(image_path)
        values: list[tuple[str, float]] = []
        for token in tokens:
            normalized = _normalize_token(token.text)
            if normalized is not None:
                values.append((normalized, token.confidence))

        target_size = 36
        targets: list[TargetReading] = []
        for target_idx in range(4):
            chunk = values[target_idx * target_size : (target_idx + 1) * target_size]
            arrows = [ArrowReading(arrow_index=i + 1, value=v, confidence=c) for i, (v, c) in enumerate(chunk)]

            ends: list[EndReading] = []
            for end_idx in range(6):
                end_arrows = arrows[end_idx * 6 : (end_idx + 1) * 6]
                subtotal = sum(_to_score(arrow.value) for arrow in end_arrows)
                ends.append(EndReading(end_index=end_idx + 1, arrows=end_arrows, subtotal=subtotal))

            total = sum(end.subtotal for end in ends)
            targets.append(TargetReading(target_index=target_idx + 1, arrows=arrows, ends=ends, total=total))

        return StructuredScoreSheet(image_path=str(image_path), targets=targets, raw_tokens=tokens)
