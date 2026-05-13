from dataclasses import asdict, dataclass


@dataclass
class SyntheticArrow:
    arrow: int
    value: str
    score_value: int


@dataclass
class SyntheticEnd:
    end: int
    arrows: list[SyntheticArrow]
    subtotal: int
    cumulative: int


@dataclass
class SyntheticTarget:
    target_index: int
    target_no: str
    rounds: list[SyntheticEnd]
    total: int
    x_count: int
    x_plus_ten_count: int


@dataclass
class SyntheticSheet:
    image_id: str
    seed: int
    targets: list[SyntheticTarget]

    def to_dict(self) -> dict:
        return asdict(self)
