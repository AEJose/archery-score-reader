from pathlib import Path

import typer

from score_reader.dataset.pipeline import DatasetPipeline
from score_reader.processing import ScoreSheetParser
from score_reader.visualization import DebugVisualizer
import json

app = typer.Typer(help="Archery score reader CLI", invoke_without_command=True)


@app.callback()
def main(
    ctx: typer.Context,
    output: Path | None = typer.Option(None, dir_okay=True, file_okay=False, help="[Deprecated] dataset output dir"),
    num_images: int = typer.Option(100, min=1, help="[Deprecated] number of images"),
    seed: int = typer.Option(1234, help="[Deprecated] random seed"),
    template: Path = typer.Option(Path("./sample.png"), exists=True, dir_okay=False, file_okay=True, help="[Deprecated] template image"),
) -> None:
    """Support subcommands and legacy root options used by old scripts."""
    if ctx.invoked_subcommand is not None:
        return
    if output is None:
        return

    typer.echo("[deprecated] using root options; please switch to: score-reader generate-dataset ...")
    pipeline = DatasetPipeline(output_dir=output, num_images=num_images, seed=seed, template_image=template)
    manifest_path = pipeline.run()
    typer.echo(f"Generated dataset manifest: {manifest_path}")


@app.command("generate-dataset")
def generate_dataset(
    output: Path = typer.Option(..., exists=False, dir_okay=True, file_okay=False),
    num_images: int = typer.Option(100, min=1),
    seed: int = typer.Option(1234),
    template: Path = typer.Option(Path("./sample.png"), exists=True, dir_okay=False, file_okay=True),
) -> None:
    """Generate synthetic dataset (MVP fake data pipeline)."""
    pipeline = DatasetPipeline(output_dir=output, num_images=num_images, seed=seed, template_image=template)
    manifest_path = pipeline.run()
    typer.echo(f"Generated dataset manifest: {manifest_path}")


@app.command("read-score-sheet")
def read_score_sheet(
    image: Path = typer.Option(..., exists=True, dir_okay=False, file_okay=True),
    output: Path = typer.Option(..., exists=False, dir_okay=False, file_okay=True),
) -> None:
    """Run OCR and convert recognized values into structured score sheet JSON."""
    parser = ScoreSheetParser()
    result = parser.parse(image)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"Structured OCR result saved: {output}")


@app.command("debug-visualize")
def debug_visualize(
    image: Path = typer.Option(..., exists=True, dir_okay=False, file_okay=True),
    output: Path = typer.Option(..., exists=False, dir_okay=True, file_okay=False),
) -> None:
    """Generate debug overlays for region/cell detection and OCR output."""
    visualizer = DebugVisualizer()
    paths = visualizer.generate(image, output)
    typer.echo("Debug overlays generated:")
    for path in paths:
        typer.echo(f"- {path}")


if __name__ == "__main__":
    app()
