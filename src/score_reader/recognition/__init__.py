from .models import StructuredScoreSheet

__all__ = ["StructuredScoreSheet", "OCREngine"]


def __getattr__(name: str):
    if name == "OCREngine":
        from .ocr_engine import OCREngine

        return OCREngine
    raise AttributeError(name)
