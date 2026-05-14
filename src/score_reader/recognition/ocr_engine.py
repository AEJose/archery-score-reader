from pathlib import Path

import cv2

from score_reader.recognition.models import OCRToken


class OCREngine:
    """OCR backend wrapper that avoids OS-level package installation.

    Uses RapidOCR (ONNX Runtime) as default because it is installable via Python
    dependencies and does not require `apt install tesseract-ocr`.
    """

    def __init__(self, language: str = "en") -> None:
        self.language = language
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "rapidocr-onnxruntime is required for OCR. Install dependencies with: uv sync"
            ) from exc

        self._engine = RapidOCR()
        return self._engine

    def run(self, image_path: Path) -> list[OCRToken]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")
        return self.run_array(image)

    def run_array(self, image) -> list[OCRToken]:
        engine = self._get_engine()
        result, _ = engine(image)

        tokens: list[OCRToken] = []
        if not result:
            return tokens

        for item in result:
            points, text, confidence = item
            xs = [int(p[0]) for p in points]
            ys = [int(p[1]) for p in points]
            left = min(xs)
            top = min(ys)
            width = max(xs) - left
            height = max(ys) - top
            tokens.append(
                OCRToken(
                    text=str(text).strip(),
                    confidence=max(0.0, min(float(confidence), 1.0)),
                    bbox=(left, top, width, height),
                )
            )

        return [token for token in tokens if token.text]
