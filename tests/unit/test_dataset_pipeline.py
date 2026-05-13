import json
from pathlib import Path

from score_reader.dataset.pipeline import DatasetPipeline


def test_dataset_pipeline_generates_manifest_and_images(tmp_path: Path) -> None:
    out = tmp_path / "generated"
    template = tmp_path / "template.png"
    template.write_bytes(b"fake-png")

    manifest = DatasetPipeline(output_dir=out, num_images=3, seed=42, template_image=template).run()
    assert manifest.exists()

    lines = manifest.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    row = json.loads(lines[0])

    assert Path(row["image"]).exists()
    assert Path(row["label"]).exists()
    assert (out / "images" / "train" / "synthetic_000001.png").exists()
    assert (out / "labels" / "train" / "synthetic_000001.json").exists()
