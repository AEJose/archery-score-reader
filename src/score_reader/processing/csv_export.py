from __future__ import annotations

import csv
from pathlib import Path

from score_reader.recognition.models import EndReading, StructuredScoreSheet, TargetReading


def _arrow_to_score(value: str) -> int:
    if value in {"X", "10"}:
        return 10
    if value == "M":
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _end_halves(end: EndReading) -> tuple[list[str], list[str]]:
    ordered = sorted(end.arrows, key=lambda a: a.arrow_index)
    upper = [a.value for a in ordered[:3]]
    lower = [a.value for a in ordered[3:6]]
    while len(upper) < 3:
        upper.append("null")
    while len(lower) < 3:
        lower.append("null")
    return upper, lower


def _csv_headers() -> list[str]:
    headers = [
        "image_path",
        "archer_index",
        "unit",
        "target_lane",
        "lane_code",
        "name",
        "final_total",
        "x_count",
        "x_plus_10_count",
        "notes",
    ]
    for i in range(1, 7):
        headers.extend(
            [
                f"end{i}_upper_arrows",
                f"end{i}_upper_subtotal",
                f"end{i}_lower_arrows",
                f"end{i}_lower_subtotal",
                f"end{i}_total",
                f"end{i}_cumulative_total",
            ]
        )
    return headers


def _target_to_row(sheet: StructuredScoreSheet, target: TargetReading, notes: str) -> dict[str, str | int]:
    values = [a.value for a in target.arrows]
    low_conf_count = sum(1 for a in target.arrows if a.confidence < 0.35)
    x_count = sum(1 for v in values if v == "X")
    x_plus_10_count = sum(1 for v in values if v in {"X", "10"})
    row: dict[str, str | int] = {
        "image_path": sheet.image_path,
        "archer_index": target.target_index,
        "unit": "null",
        "target_lane": target.target_index,
        "lane_code": "null",
        "name": "null",
        "final_total": target.total,
        "x_count": x_count,
        "x_plus_10_count": x_plus_10_count,
        "notes": f"{notes} | low_conf_cells={low_conf_count}",
    }
    cumulative = 0
    ends = {e.end_index: e for e in target.ends}
    for i in range(1, 7):
        end = ends.get(i, EndReading(end_index=i, arrows=[]))
        upper, lower = _end_halves(end)
        upper_subtotal = sum(_arrow_to_score(v) for v in upper if v != "null")
        lower_subtotal = sum(_arrow_to_score(v) for v in lower if v != "null")
        total = upper_subtotal + lower_subtotal
        cumulative += total
        row[f"end{i}_upper_arrows"] = "/".join(upper)
        row[f"end{i}_upper_subtotal"] = upper_subtotal if upper != ["null", "null", "null"] else "null"
        row[f"end{i}_lower_arrows"] = "/".join(lower)
        row[f"end{i}_lower_subtotal"] = lower_subtotal if lower != ["null", "null", "null"] else "null"
        row[f"end{i}_total"] = total if end.arrows else "null"
        row[f"end{i}_cumulative_total"] = cumulative if end.arrows else "null"
    return row


def write_score_sheet_csv(sheet: StructuredScoreSheet, output_path: Path, notes: str = "") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = _csv_headers()
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for target in sheet.targets:
            writer.writerow(_target_to_row(sheet, target, notes=notes))

