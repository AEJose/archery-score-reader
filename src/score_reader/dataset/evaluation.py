import json
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DetectionMetrics:
    total_arrows: int
    correct_arrows: int
    arrow_accuracy: float
    total_targets: int
    correct_totals: int
    total_accuracy: float

    def to_dict(self) -> dict:
        return {
            "total_arrows": self.total_arrows,
            "correct_arrows": self.correct_arrows,
            "arrow_accuracy": round(self.arrow_accuracy, 4),
            "total_targets": self.total_targets,
            "correct_totals": self.correct_totals,
            "total_accuracy": round(self.total_accuracy, 4),
        }


class BaselineDetector:
    """Baseline detector for evaluation workflow.

    - In `oracle` mode: returns perfect prediction (for pipeline sanity check).
    - In `noisy` mode: introduces configurable noise to simulate recognition errors.
    """

    def __init__(self, mode: str = "noisy", error_rate: float = 0.1, seed: int = 2026) -> None:
        if mode not in {"oracle", "noisy"}:
            raise ValueError("mode must be one of: oracle, noisy")
        if not 0 <= error_rate <= 1:
            raise ValueError("error_rate must be between 0 and 1")
        self.mode = mode
        self.error_rate = error_rate
        self.rng = random.Random(seed)
        self.classes = ["X", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "M"]

    def predict_sheet(self, ground_truth: dict) -> dict:
        prediction = json.loads(json.dumps(ground_truth))
        if self.mode == "oracle":
            return prediction

        for target in prediction["targets"]:
            for end in target["rounds"]:
                for arrow in end["arrows"]:
                    if self.rng.random() < self.error_rate:
                        original = arrow["value"]
                        candidates = [x for x in self.classes if x != original]
                        arrow["value"] = self.rng.choice(candidates)
                        arrow["score_value"] = 10 if arrow["value"] in {"X", "10"} else (0 if arrow["value"] == "M" else int(arrow["value"]))

            # recompute per-target totals from predicted arrows
            total = 0
            x_count = 0
            x10_count = 0
            for end in target["rounds"]:
                subtotal = sum(a["score_value"] for a in end["arrows"])
                total += subtotal
                end["subtotal"] = subtotal
                end["cumulative"] = total
                x_count += sum(1 for a in end["arrows"] if a["value"] == "X")
                x10_count += sum(1 for a in end["arrows"] if a["score_value"] == 10)
            target["total"] = total
            target["x_count"] = x_count
            target["x_plus_ten_count"] = x10_count

        return prediction


def load_manifest(manifest_path: Path) -> list[dict]:
    records: list[dict] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def evaluate_dataset(manifest_path: Path, output_dir: Path, detector: BaselineDetector) -> Path:
    records = load_manifest(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_arrows = correct_arrows = 0
    total_targets = correct_totals = 0
    per_sheet: list[dict] = []

    for rec in records:
        gt = json.loads(Path(rec["label"]).read_text(encoding="utf-8"))
        pred = detector.predict_sheet(gt)

        sheet_total = sheet_correct = 0
        sheet_targets = sheet_targets_correct = 0

        for gt_t, pred_t in zip(gt["targets"], pred["targets"]):
            sheet_targets += 1
            if gt_t["total"] == pred_t["total"]:
                sheet_targets_correct += 1
            for gt_e, pred_e in zip(gt_t["rounds"], pred_t["rounds"]):
                for gt_a, pred_a in zip(gt_e["arrows"], pred_e["arrows"]):
                    sheet_total += 1
                    if gt_a["value"] == pred_a["value"]:
                        sheet_correct += 1

        total_arrows += sheet_total
        correct_arrows += sheet_correct
        total_targets += sheet_targets
        correct_totals += sheet_targets_correct

        per_sheet.append(
            {
                "image_id": gt["image_id"],
                "arrow_accuracy": round(sheet_correct / sheet_total, 4) if sheet_total else 0,
                "total_accuracy": round(sheet_targets_correct / sheet_targets, 4) if sheet_targets else 0,
            }
        )

    metrics = DetectionMetrics(
        total_arrows=total_arrows,
        correct_arrows=correct_arrows,
        arrow_accuracy=(correct_arrows / total_arrows) if total_arrows else 0,
        total_targets=total_targets,
        correct_totals=correct_totals,
        total_accuracy=(correct_totals / total_targets) if total_targets else 0,
    )

    result = {"summary": metrics.to_dict(), "per_sheet": per_sheet}
    out_path = output_dir / "detection_eval.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
