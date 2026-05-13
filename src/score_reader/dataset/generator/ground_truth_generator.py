import random

from score_reader.dataset.models import SyntheticArrow, SyntheticEnd, SyntheticTarget

VALUES = ["X", "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "M"]


def _to_score(value: str) -> int:
    if value in {"X", "10"}:
        return 10
    if value == "M":
        return 0
    return int(value)


class GroundTruthGenerator:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def generate_target(self, target_index: int) -> SyntheticTarget:
        cumulative = 0
        rounds: list[SyntheticEnd] = []
        x_count = 0
        x10_count = 0
        for end_no in range(1, 7):
            arrows: list[SyntheticArrow] = []
            subtotal = 0
            sampled_values = [self.rng.choice(VALUES) for _ in range(6)]
            # 在每一輪內，分數由高到低排序，符合實際填寫習慣。
            sampled_values.sort(key=_to_score, reverse=True)

            for arrow_no, value in enumerate(sampled_values, start=1):
                score = _to_score(value)
                subtotal += score
                if value == "X":
                    x_count += 1
                if score == 10:
                    x10_count += 1
                arrows.append(SyntheticArrow(arrow=arrow_no, value=value, score_value=score))
            cumulative += subtotal
            rounds.append(SyntheticEnd(end=end_no, arrows=arrows, subtotal=subtotal, cumulative=cumulative))

        return SyntheticTarget(
            target_index=target_index,
            target_no=f"{target_index + 1}A",
            rounds=rounds,
            total=cumulative,
            x_count=x_count,
            x_plus_ten_count=x10_count,
        )
