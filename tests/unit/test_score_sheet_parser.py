from pathlib import Path

from score_reader.processing.score_sheet_parser import ScoreSheetParser
from score_reader.recognition.models import OCRToken


class FakeOCREngine:
    def run(self, image_path: Path) -> list[OCRToken]:
        tokens = []
        for _ in range(4):
            for v in ["10", "9", "8", "7", "6", "5"] * 6:
                tokens.append(OCRToken(text=v, confidence=0.9, bbox=(0, 0, 10, 10)))
        return tokens


def test_parser_builds_structured_targets() -> None:
    parser = ScoreSheetParser(ocr_engine=FakeOCREngine())
    result = parser.parse(Path("dummy.png"))

    assert len(result.targets) == 4
    assert result.targets[0].ends[0].subtotal == 45
    assert result.targets[0].total == 270
    assert result.targets[0].arrows[0].value == "10"
