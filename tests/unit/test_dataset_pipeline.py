import json
from pathlib import Path

from PIL import Image

from score_reader.dataset.pipeline import DatasetPipeline
from score_reader.dataset.generator.sheet_renderer import SheetRenderer


def test_dataset_pipeline_generates_manifest_and_images(tmp_path: Path) -> None:
    out = tmp_path / "generated"
    template = tmp_path / "template.png"
    Image.new("RGB", (1200, 1800), "white").save(template)

    manifest = DatasetPipeline(output_dir=out, num_images=3, seed=42, template_image=template).run()
    assert manifest.exists()

    lines = manifest.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    row = json.loads(lines[0])

    assert Path(row["image"]).exists()
    assert Path(row["label"]).exists()
    assert (out / "images" / "train" / "synthetic_000001.png").exists()
    assert (out / "labels" / "train" / "synthetic_000001.json").exists()


def test_sheet_renderer_orientation_variants_cover_vertical_and_upside_down() -> None:
    renderer = SheetRenderer(seed=42)
    image = Image.new("RGB", (200, 300), "white")

    seen_sizes: set[tuple[int, int]] = set()
    saw_upside_down = False
    for _ in range(100):
        rotated = renderer._apply_orientation_variant(image)
        seen_sizes.add(rotated.size)
        if rotated.size == image.size and rotated.tobytes() == image.rotate(180).tobytes():
            saw_upside_down = True

    assert (200, 300) in seen_sizes
    assert (300, 200) in seen_sizes
    assert saw_upside_down
