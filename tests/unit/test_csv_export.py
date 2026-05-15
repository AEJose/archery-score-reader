from pathlib import Path

from score_reader.processing.csv_export import write_score_sheet_csv
from score_reader.recognition.models import ArrowReading, EndReading, StructuredScoreSheet, TargetReading


def test_write_score_sheet_csv_outputs_expected_columns(tmp_path: Path) -> None:
    ends = [
        EndReading(
            end_index=1,
            arrows=[
                ArrowReading(arrow_index=1, value="10", confidence=0.9),
                ArrowReading(arrow_index=2, value="X", confidence=0.9),
                ArrowReading(arrow_index=3, value="9", confidence=0.9),
                ArrowReading(arrow_index=4, value="8", confidence=0.9),
                ArrowReading(arrow_index=5, value="7", confidence=0.9),
                ArrowReading(arrow_index=6, value="M", confidence=0.9),
            ],
            subtotal=44,
        )
    ] + [EndReading(end_index=i, arrows=[], subtotal=0) for i in range(2, 7)]

    target = TargetReading(target_index=1, arrows=ends[0].arrows, ends=ends, total=44)
    sheet = StructuredScoreSheet(image_path="./sample.png", targets=[target], raw_tokens=[])
    out = tmp_path / "out.csv"

    write_score_sheet_csv(sheet, out)

    text = out.read_text(encoding="utf-8")
    assert "image_path,archer_index,unit,target_lane,lane_code,name,final_total" in text
    assert "end1_upper_arrows,end1_upper_subtotal,end1_lower_arrows,end1_lower_subtotal,end1_total,end1_cumulative_total" in text
    assert "./sample.png,1,null,1,null,null,44,1,2," in text
    assert "10/X/9,29,8/7/M,15,44,44" in text
