"""Typer-based command-line interface."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from knowledge_capture import __version__
from knowledge_capture.config import CrawlConfig
from knowledge_capture.pipeline import inspect_url, run_crawl

app = typer.Typer(
    name="kcap",
    help="Crawl documentation sites and emit AI-friendly Markdown.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


def _setup_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", help="Show version and exit"),
) -> None:
    if version:
        console.print(f"knowledge-capture {__version__}")
        raise typer.Exit()


@app.command()
def crawl(
    url: Annotated[str, typer.Argument(help="Seed URL to start the crawl from")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output directory")] = Path("./out"),
    scope: Annotated[str, typer.Option(help="prefix | domain | custom")] = "prefix",
    include: Annotated[list[str] | None, typer.Option("--include", help="URL must match this regex (repeatable)")] = None,
    exclude: Annotated[list[str] | None, typer.Option("--exclude", help="Drop URLs matching this regex (repeatable)")] = None,
    fetcher: Annotated[str, typer.Option(help="auto | http | browser")] = "auto",
    max_pages: Annotated[int, typer.Option("--max-pages", help="Cap on total pages")] = 1000,
    max_depth: Annotated[int, typer.Option("--max-depth", help="BFS depth cap")] = 10,
    concurrency: Annotated[int, typer.Option("--concurrency", "-c")] = 8,
    rate: Annotated[float, typer.Option("--rate", help="Per-host requests per second")] = 4.0,
    use_llm: Annotated[bool, typer.Option("--use-llm", help="LLM-assisted profile fallback")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Bypass the HTTP cache")] = False,
    cache_dir: Annotated[Path, typer.Option("--cache-dir")] = Path("./.kcap-cache"),
    obey_robots: Annotated[bool, typer.Option("--obey-robots/--ignore-robots")] = True,
    user_agent: Annotated[str | None, typer.Option("--user-agent", "-A")] = None,
    site_title: Annotated[str | None, typer.Option("--site-title")] = None,
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True)] = 0,
) -> None:
    """Crawl a documentation site and write AI-friendly markdown."""

    if exclude is None:
        exclude = []
    if include is None:
        include = []
    _setup_logging(verbose)

    overrides: dict[str, object] = {
        "output_dir": output,
        "scope": scope,
        "include_patterns": list(include or []),
        "exclude_patterns": list(exclude or []),
        "fetcher": fetcher,
        "max_pages": max_pages,
        "max_depth": max_depth,
        "concurrency": concurrency,
        "rate_limit_rps": rate,
        "use_llm_detection": use_llm,
        "cache_dir": Path("/dev/null") if no_cache else cache_dir,
        "obey_robots": obey_robots,
        "site_title": site_title,
    }
    if user_agent:
        overrides["user_agent"] = user_agent

    config = CrawlConfig(seed_url=url, **{k: v for k, v in overrides.items() if v is not None})  # type: ignore[arg-type]

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    task_id = progress.add_task("Crawling", total=config.max_pages)

    def on_page(page: object) -> None:
        progress.update(task_id, advance=1, description=f"Crawling: {getattr(page, 'title', '')[:60]}")

    with progress:
        result = asyncio.run(run_crawl(config, progress=on_page))

    console.print()
    console.print(f"[green]Done.[/green] Output: [bold]{config.output_dir}[/bold]")
    console.print(
        f"  pages fetched: {result.stats.pages_fetched}, "
        f"written: {result.stats.pages_written}, "
        f"failed: {result.stats.pages_failed}, "
        f"deduped: {result.stats.duplicates_dropped}, "
        f"js fetches: {result.stats.js_fetches}"
    )
    if result.errors:
        console.print(f"[yellow]{len(result.errors)} errors[/yellow] (see manifest.json)")


@app.command()
def inspect(
    url: Annotated[str, typer.Argument(help="URL to inspect")],
    use_llm: Annotated[bool, typer.Option("--use-llm")] = False,
    show_markdown: Annotated[bool, typer.Option("--show-markdown/--no-show-markdown")] = True,
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True)] = 0,
) -> None:
    """Detect a site's profile and dump a sample extracted page."""

    _setup_logging(verbose)
    info = asyncio.run(inspect_url(url, use_llm=use_llm))
    profile = info["profile"]
    page = info["page"]

    console.rule("Detected Profile")
    console.print(profile)
    console.rule("Page Metadata")
    console.print(
        {
            "title": getattr(page, "title", None),
            "canonical_url": getattr(page, "canonical_url", None),
            "breadcrumbs": getattr(page, "breadcrumbs", None),
            "outlinks": len(getattr(page, "outlinks", []) or []),
            "fetcher": getattr(page, "fetcher_used", None),
            "relative_path": getattr(page, "relative_path", None),
        }
    )
    if show_markdown:
        console.rule("Markdown (truncated)")
        md = info["markdown"]
        if isinstance(md, str):
            preview = md if len(md) <= 4000 else md[:4000] + "\n\n... [truncated] ...\n"
            console.print(preview)


if __name__ == "__main__":
    app()
