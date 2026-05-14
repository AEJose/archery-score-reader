from pathlib import Path

from score_reader.processing.score_sheet_parser import ScoreSheetParser
from score_reader.dataset.generator.sheet_renderer import Cell
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


def test_classify_arrow_cells_uses_top_scoring_rows() -> None:
    parser = ScoreSheetParser(ocr_engine=FakeOCREngine())

    rows = []
    for row_idx in range(14):
        rows.append([Cell(col * 10, row_idx * 10, col * 10 + 8, row_idx * 10 + 8) for col in range(6)])

    arrow_cells = parser._classify_arrow_cells(rows)

    assert len(arrow_cells) == 36
    assert arrow_cells[0] == (1, 1, rows[0][0])
    assert arrow_cells[-1] == (6, 6, rows[11][2])
