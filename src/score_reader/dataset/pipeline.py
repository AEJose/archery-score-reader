import json
import random
import shutil
from pathlib import Path

from score_reader.dataset.generator.ground_truth_generator import GroundTruthGenerator
from score_reader.dataset.models import SyntheticSheet


class DatasetPipeline:
    def __init__(self, output_dir: Path, num_images: int, seed: int, template_image: Path) -> None:
        self.output_dir = output_dir
        self.num_images = num_images
        self.seed = seed
        self.template_image = template_image

    def run(self) -> Path:
        if not self.template_image.exists():
            raise FileNotFoundError(f"Template image not found: {self.template_image}")

        rng = random.Random(self.seed)
        generator = GroundTruthGenerator(rng)

        images_dir = self.output_dir / "images" / "train"
        labels_dir = self.output_dir / "labels" / "train"
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = self.output_dir / "manifest.jsonl"
        with manifest_path.open("w", encoding="utf-8") as manifest:
            for i in range(1, self.num_images + 1):
                image_id = f"synthetic_{i:06d}"
                targets = [generator.generate_target(idx) for idx in range(4)]
                sheet = SyntheticSheet(image_id=image_id, seed=self.seed + i, targets=targets)

                image_path = images_dir / f"{image_id}.png"
                shutil.copy2(self.template_image, image_path)

                label_path = labels_dir / f"{image_id}.json"
                label_path.write_text(json.dumps(sheet.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

                manifest.write(
                    json.dumps(
                        {"image_id": image_id, "image": str(image_path), "label": str(label_path)},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        return manifest_path
