from pathlib import Path

import typer

from score_reader.dataset.pipeline import DatasetPipeline

app = typer.Typer(help="Archery score reader CLI")


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


if __name__ == "__main__":
    app()
