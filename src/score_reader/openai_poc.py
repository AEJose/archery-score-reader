from __future__ import annotations

import base64
import csv
import json
from pathlib import Path
from typing import Literal

import cv2
import typer
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

app = typer.Typer(help="OpenAI multimodal archery score-sheet OCR POC")


class ArrowGroup(BaseModel):
    row_type: Literal["upper_3", "lower_3"] = Field(description="Upper half end (3 arrows) or lower half end (3 arrows)")
    arrows: list[str] = Field(default_factory=list, description="Exactly 3 values: X,10..1,M,blank")
    subtotal: int | None = Field(default=None)


class EndResult(BaseModel):
    end_index: int
    upper_3: ArrowGroup
    lower_3: ArrowGroup
    end_total: int | None = None
    cumulative_total: int | None = None


class ArcherBlock(BaseModel):
    archer_index: int
    unit: str | None = Field(default=None, description="Archer unit/school/org; null if missing")
    target_lane: str | None = Field(default=None, description="Shared target lane number/text; null if missing")
    lane_code: str | None = Field(default=None, description="Like 1A, 1B, 2E, 3C")
    name: str | None = Field(default=None, description="Archer name; null if missing")
    ends: list[EndResult] = Field(default_factory=list, max_length=6)
    final_total: int | None = None
    x_count: int | None = None
    x_plus_10_count: int | None = None


class ScoreSheetResult(BaseModel):
    image_path: str
    archers: list[ArcherBlock] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _encode_image_bytes(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _read_image(path: Path) -> bytes:
    return path.read_bytes()


def _rotate_image_bytes(image_bytes: bytes, rotation: int) -> bytes:
    import numpy as np

    arr = cv2.imdecode(np.frombuffer(image_bytes, dtype="uint8"), cv2.IMREAD_COLOR)
    if arr is None:
        return image_bytes
    if rotation == 90:
        arr = cv2.rotate(arr, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        arr = cv2.rotate(arr, cv2.ROTATE_180)
    elif rotation == 270:
        arr = cv2.rotate(arr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    ok, enc = cv2.imencode(".jpg", arr)
    return enc.tobytes() if ok else image_bytes






def _resize_longest_edge(image_bytes: bytes, max_long_edge: int = 2000) -> bytes:
    import numpy as np

    arr = cv2.imdecode(np.frombuffer(image_bytes, dtype="uint8"), cv2.IMREAD_COLOR)
    if arr is None:
        return image_bytes

    height, width = arr.shape[:2]
    long_edge = max(height, width)
    if long_edge <= max_long_edge:
        return image_bytes

    scale = max_long_edge / float(long_edge)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    resized = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    ok, enc = cv2.imencode('.jpg', resized)
    return enc.tobytes() if ok else image_bytes

def _candidate_rotations(image_bytes: bytes) -> list[int]:
    import numpy as np

    arr = cv2.imdecode(np.frombuffer(image_bytes, dtype="uint8"), cv2.IMREAD_COLOR)
    if arr is None:
        return [0, 180]

    height, width = arr.shape[:2]
    # Use traditional CV heuristic by aspect ratio to reduce model calls:
    # - portrait: only need 90 or 270
    # - landscape/square: only need 0 or 180
    if height > width:
        return [90, 270]
    return [0, 180]

def _extract_one_image(client: OpenAI, model: str, image_bytes: bytes) -> ScoreSheetResult:
    b64 = _encode_image_bytes(image_bytes)
    prompt = (
        "You are reading an archery paper score sheet. Return strictly valid JSON only. "
        "Scoring rules: X=10 points, 10=10 points, 9..1 as numeric points, M=0 points. "
        "A full round has 6 ends, each end has 6 arrows split into upper half end 3 arrows and lower half end 3 arrows, total 36 arrows. "
        "Extract as complete as possible: each archer's unit, target lane, lane_code, name, and up to 6 ends with arrow values, subtotals, end totals, cumulative totals, final total. If an archer did not finish (retired/DNF) or the sheet is partially filled, keep missing ends as null/empty. If identity fields are missing on the sheet (name, unit, target lane, lane_code), keep them null and continue extracting scores. A sheet is shared by one target lane and can contain 1 to 6 archers (commonly 4), lane codes can be like 1A/1B/1C/1D, 2E/2F, or 3A/3B/3C. "
        "Preserve uncertain fields as null and explain in notes."
    )

    schema = ScoreSheetResult.model_json_schema()
    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_schema", "json_schema": {"name": "archery_score_sheet", "schema": schema, "strict": True}},
        messages=[
            {"role": "system", "content": "You are a precise OCR extraction assistant."},
            {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]},
        ],
    )
    content = completion.choices[0].message.content or "{}"
    data = json.loads(content)
    return ScoreSheetResult.model_validate(data)


def _normalize_arrow(v: str) -> str:
    token = (v or "").strip().upper()
    if token == "":
        return ""
    if token in {"X", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "M"}:
        return token
    return token


def _populate_counts(result: ScoreSheetResult) -> None:
    for archer in result.archers:
        arrows: list[str] = []
        for end in archer.ends:
            arrows.extend(_normalize_arrow(a) for a in end.upper_3.arrows)
            arrows.extend(_normalize_arrow(a) for a in end.lower_3.arrows)
        archer.x_count = sum(1 for a in arrows if a == "X")
        archer.x_plus_10_count = sum(1 for a in arrows if a in {"X", "10"})




def _candidate_quality_score(candidate: ScoreSheetResult) -> int:
    """Heuristic quality score for early-exit selection."""
    score = 0
    for archer in candidate.archers:
        if archer.name:
            score += 2
        if archer.unit:
            score += 1
        if archer.target_lane or archer.lane_code:
            score += 1
        score += len(archer.ends) * 5
        for end in archer.ends:
            if end.end_total is not None:
                score += 1
            if end.cumulative_total is not None:
                score += 1
    return score


def _is_quality_good_enough(candidate: ScoreSheetResult) -> bool:
    """Stop early when structure is already good enough to avoid extra API call."""
    if not candidate.archers:
        return False

    # Good enough if all detected archers have >= 5 ends parsed
    # (allows one missing end for DNF/partial sheets), and at least one identity signal exists.
    enough_ends = all(len(a.ends) >= 5 for a in candidate.archers)
    has_identity = any((a.name or a.unit or a.target_lane or a.lane_code) for a in candidate.archers)
    return enough_ends and has_identity

def _extract_with_orientation(client: OpenAI, model: str, image_path: Path) -> ScoreSheetResult:
    original = _read_image(image_path)
    normalized = _resize_longest_edge(original, max_long_edge=2000)
    rotations = _candidate_rotations(normalized)
    variants = [(rot, _rotate_image_bytes(normalized, rot)) for rot in rotations]

    best: ScoreSheetResult | None = None
    best_score = -1
    for idx, (rot, img) in enumerate(variants):
        candidate = _extract_one_image(client, model, img)
        score = _candidate_quality_score(candidate)
        if score > best_score:
            best_score = score
            best = candidate
            if "notes" not in candidate.model_fields_set:
                candidate.notes = []
            candidate.notes.append(f"selected_rotation={rot}")

        # Early-exit: first candidate already good enough, skip second orientation to save cost.
        if idx == 0 and _is_quality_good_enough(candidate):
            candidate.notes.append("early_exit_after_first_rotation")
            best = candidate
            break

    if best is None:
        raise RuntimeError("Failed to extract score sheet.")

    best.image_path = str(image_path)
    if normalized != original:
        best.notes.append("resized_long_edge_to<=2000")
    _populate_counts(best)
    return best


def _iter_images(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in exts)


def _write_csv(results: list[ScoreSheetResult], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "image_path", "archer_index", "unit", "target_lane", "lane_code", "name", "final_total", "x_count", "x_plus_10_count", "notes"
    ]
    for end_idx in range(1, 7):
        headers.extend([
            f"end{end_idx}_upper_arrows",
            f"end{end_idx}_upper_subtotal",
            f"end{end_idx}_lower_arrows",
            f"end{end_idx}_lower_subtotal",
            f"end{end_idx}_total",
            f"end{end_idx}_cumulative_total",
        ])

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for result in results:
            notes = " | ".join(result.notes)
            for archer in result.archers:
                row = {
                    "image_path": result.image_path,
                    "archer_index": archer.archer_index,
                    "unit": archer.unit,
                    "target_lane": archer.target_lane,
                    "lane_code": archer.lane_code,
                    "name": archer.name,
                    "final_total": archer.final_total,
                    "x_count": archer.x_count,
                    "x_plus_10_count": archer.x_plus_10_count,
                    "notes": notes,
                }
                ends_by_idx = {e.end_index: e for e in archer.ends}
                for end_idx in range(1, 7):
                    end = ends_by_idx.get(end_idx)
                    if end is None:
                        row[f"end{end_idx}_upper_arrows"] = ""
                        row[f"end{end_idx}_upper_subtotal"] = None
                        row[f"end{end_idx}_lower_arrows"] = ""
                        row[f"end{end_idx}_lower_subtotal"] = None
                        row[f"end{end_idx}_total"] = None
                        row[f"end{end_idx}_cumulative_total"] = None
                    else:
                        row[f"end{end_idx}_upper_arrows"] = "/".join(end.upper_3.arrows)
                        row[f"end{end_idx}_upper_subtotal"] = end.upper_3.subtotal
                        row[f"end{end_idx}_lower_arrows"] = "/".join(end.lower_3.arrows)
                        row[f"end{end_idx}_lower_subtotal"] = end.lower_3.subtotal
                        row[f"end{end_idx}_total"] = end.end_total
                        row[f"end{end_idx}_cumulative_total"] = end.cumulative_total
                writer.writerow(row)


@app.command("extract")
def extract(
    input_path: Path = typer.Option(..., exists=True, help="Single image file or folder path"),
    output_csv: Path = typer.Option(Path("./out/openai_ocr.csv"), help="Output CSV file"),
    output_json: Path = typer.Option(Path("./out/openai_ocr.json"), help="Full JSON output"),
    model: str = typer.Option("gpt-5.5", help="Multimodal model name"),
) -> None:
    load_dotenv()
    client = OpenAI()
    image_paths = _iter_images(input_path)
    if not image_paths:
        raise typer.BadParameter("No supported image files found.")

    results: list[ScoreSheetResult] = []
    for image_path in image_paths:
        typer.echo(f"Processing: {image_path}")
        results.append(_extract_with_orientation(client, model, image_path))

    _write_csv(results, output_csv)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps([r.model_dump(mode="json") for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"Done. CSV: {output_csv}")
    typer.echo(f"Done. JSON: {output_json}")


if __name__ == "__main__":
    app()
