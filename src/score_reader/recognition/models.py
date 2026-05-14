from dataclasses import asdict, dataclass, field


@dataclass
class OCRToken:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass
class ArrowReading:
    arrow_index: int
    value: str
    confidence: float


@dataclass
class EndReading:
    end_index: int
    arrows: list[ArrowReading] = field(default_factory=list)
    subtotal: int = 0


@dataclass
class TargetReading:
    target_index: int
    arrows: list[ArrowReading] = field(default_factory=list)
    ends: list[EndReading] = field(default_factory=list)
    total: int = 0


@dataclass
class StructuredScoreSheet:
    image_path: str
    targets: list[TargetReading]
    raw_tokens: list[OCRToken]

    def to_dict(self) -> dict:
        return asdict(self)
