from pathlib import Path

import cv2

from score_reader.recognition.models import OCRToken


class OCREngine:
    def __init__(self, language: str = "eng") -> None:
        self.language = language

    def run(self, image_path: Path) -> list[OCRToken]:
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("pytesseract is required for OCR. Install with: pip install pytesseract") from exc

        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")

        data = pytesseract.image_to_data(image, lang=self.language, output_type=pytesseract.Output.DICT)
        tokens: list[OCRToken] = []
        for i, raw in enumerate(data["text"]):
            text = raw.strip()
            if not text:
                continue
            try:
                confidence = float(data["conf"][i])
            except (ValueError, TypeError):
                confidence = 0.0
            bbox = (
                int(data["left"][i]),
                int(data["top"][i]),
                int(data["width"][i]),
                int(data["height"][i]),
            )
            tokens.append(OCRToken(text=text, confidence=max(0.0, confidence) / 100.0, bbox=bbox))
        return tokens
