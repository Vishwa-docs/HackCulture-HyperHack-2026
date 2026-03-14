"""CLI entry point for the needle finder pipeline."""
import typer
from pathlib import Path
from typing import Optional

app = typer.Typer(
    name="needle",
    help="Financial Needle in the Haystack - AP Bundle Error Detection Pipeline",
    add_completion=False,
)


@app.command()
def run_all(
    input_pdf: str = typer.Option("data/input/gauntlet.pdf", "--input", "-i", help="Path to gauntlet.pdf"),
    team_id: str = typer.Option("hackculture", "--team-id", "-t", help="Team ID for submission"),
    from_stage: int = typer.Option(1, "--from-stage", help="Start from this stage"),
    to_stage: int = typer.Option(99, "--to-stage", help="Stop after this stage"),
    only_category: Optional[str] = typer.Option(None, "--only-category", help="Run only this detector category"),
    limit_pages: int = typer.Option(0, "--limit-pages", help="Limit to N pages (0=all)"),
    resume: bool = typer.Option(False, "--resume", help="Resume from cached data"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    use_agents: bool = typer.Option(False, "--use-agents", help="Use LangGraph multi-agent pipeline for detection"),
):
    """Run the full pipeline end-to-end."""
    from .pipelines.run_all import Pipeline

    pdf_path = Path(input_pdf)
    if not pdf_path.is_absolute():
        pdf_path = Path(__file__).parent.parent / input_pdf

    pipeline = Pipeline(pdf_path=pdf_path, team_id=team_id)
    pipeline.run_all(
        from_stage=from_stage,
        to_stage=to_stage,
        only_category=only_category,
        limit_pages=limit_pages,
        resume=resume,
        debug=debug,
        use_agents=use_agents,
    )


@app.command()
def ingest(
    input_pdf: str = typer.Option("data/input/gauntlet.pdf", "--input", "-i"),
    limit_pages: int = typer.Option(0, "--limit-pages"),
):
    """Parse and split the PDF."""
    from .pipelines.run_all import Pipeline

    pdf_path = Path(input_pdf)
    if not pdf_path.is_absolute():
        pdf_path = Path(__file__).parent.parent / input_pdf

    pipeline = Pipeline(pdf_path=pdf_path)
    pipeline.run_all(from_stage=1, to_stage=2, limit_pages=limit_pages)


@app.command()
def extract():
    """Extract canonical entities from parsed documents."""
    from .pipelines.run_all import Pipeline
    pipeline = Pipeline()
    pipeline.run_all(from_stage=3, to_stage=4)


@app.command()
def index():
    """Build indexes from extracted data."""
    from .pipelines.run_all import Pipeline
    pipeline = Pipeline()
    pipeline.run_all(from_stage=5, to_stage=5)


@app.command()
def detect(
    only_category: Optional[str] = typer.Option(None, "--only-category"),
    use_agents: bool = typer.Option(False, "--use-agents", help="Use LangGraph multi-agent pipeline for detection"),
):
    """Run error detectors."""
    from .pipelines.run_all import Pipeline
    pipeline = Pipeline()
    pipeline.run_all(from_stage=6, to_stage=6, only_category=only_category, use_agents=use_agents)


@app.command()
def finalize(
    team_id: str = typer.Option("hackculture", "--team-id", "-t"),
):
    """Adjudicate and generate final submission JSON."""
    from .pipelines.run_all import Pipeline
    pipeline = Pipeline(team_id=team_id)
    pipeline.run_all(from_stage=7, to_stage=7)


@app.command()
def bootstrap():
    """Create all required directories and verify setup."""
    from .core import paths
    import os

    typer.echo("Checking project structure...")
    dirs = [
        paths.INPUT, paths.RAW, paths.PARSED, paths.RENDERED,
        paths.SPLIT_DOCS, paths.EXTRACTED, paths.NORMALIZED,
        paths.INDEXES, paths.OUTPUTS, paths.CACHE, paths.EVAL,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        typer.echo(f"  ✓ {d.relative_to(paths.PROJECT_ROOT)}")

    # Check PDF
    if paths.GAUNTLET_PDF.exists():
        size_mb = paths.GAUNTLET_PDF.stat().st_size / (1024 * 1024)
        typer.echo(f"  ✓ gauntlet.pdf found ({size_mb:.1f} MB)")
    else:
        typer.echo("  ✗ gauntlet.pdf NOT FOUND - place it in data/input/")

    # Check env vars
    env_vars = ["HYPERAPI_KEY", "BEDROCK_API_KEY", "AWS_ACCESS_KEY_ID"]
    for var in env_vars:
        val = os.environ.get(var, "")
        status = "✓" if val else "✗"
        typer.echo(f"  {status} {var}")

    typer.echo("\nBootstrap complete!")


if __name__ == "__main__":
    app()
