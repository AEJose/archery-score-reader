import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class ImageQualityResult:
    image_path: str
    width: int
    height: int
    estimated_skew_deg: float
    orientation: str
    shadow_ratio: float
    blur_score: float

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "width": self.width,
            "height": self.height,
            "estimated_skew_deg": round(self.estimated_skew_deg, 3),
            "orientation": self.orientation,
            "shadow_ratio": round(self.shadow_ratio, 4),
            "blur_score": round(self.blur_score, 3),
        }


def _estimate_skew_angle(gray: np.ndarray) -> float:
    edges = cv2.Canny(gray, 80, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=80, maxLineGap=12)
    if lines is None:
        return 0.0
    angles = []
    for line in lines[:, 0]:
        x1, y1, x2, y2 = line
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if -45 <= angle <= 45:
            angles.append(angle)
    if not angles:
        return 0.0
    return float(np.median(angles))


def _estimate_orientation(gray: np.ndarray) -> str:
    h, w = gray.shape
    return "portrait" if h >= w else "landscape"


def _estimate_shadow_ratio(gray: np.ndarray) -> float:
    # Pixels too dark are treated as potential shadow area.
    return float(np.mean(gray < 60))


def _estimate_blur(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def analyze_image_quality(image_path: Path) -> ImageQualityResult:
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot open image: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    return ImageQualityResult(
        image_path=str(image_path),
        width=img.shape[1],
        height=img.shape[0],
        estimated_skew_deg=_estimate_skew_angle(gray),
        orientation=_estimate_orientation(gray),
        shadow_ratio=_estimate_shadow_ratio(gray),
        blur_score=_estimate_blur(gray),
    )


def analyze_folder(images_dir: Path, output_path: Path) -> Path:
    results = []
    for p in sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg")) + sorted(images_dir.glob("*.jpeg")):
        results.append(analyze_image_quality(p).to_dict())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
