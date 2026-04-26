"""Write captured pages to disk: per-page md, bundle, llms.txt, manifest, index."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from knowledge_capture.models import CrawlResult, Page
from knowledge_capture.postprocess import add_frontmatter

log = logging.getLogger(__name__)


def write_pages(pages: list[Page], output_dir: Path, *, site_name: str | None = None) -> None:
    """Write each page as a Markdown file mirroring its URL path."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for page in pages:
        if not page.relative_path:
            log.warning("Page has no relative_path, skipping: %s", page.url)
            continue
        target = output_dir / page.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        text = add_frontmatter(page, site_name=site_name)
        target.write_text(text, encoding="utf-8")


def write_bundle(pages: list[Page], path: Path, *, site_title: str) -> None:
    """Concatenate all pages into a single markdown bundle."""

    path.parent.mkdir(parents=True, exist_ok=True)
    parts: list[str] = [f"# {site_title}\n", f"_{len(pages)} pages captured by kcap._\n"]
    for page in pages:
        parts.append("\n\n---\n\n")
        parts.append(f"# {page.title}\n")
        if page.breadcrumbs:
            parts.append(f"_{' > '.join(page.breadcrumbs)}_\n")
        parts.append(f"\n_Source: <{page.url}>_\n\n")
        parts.append(page.markdown.strip())
        parts.append("\n")
    path.write_text("".join(parts), encoding="utf-8")


def write_llms_txt(pages: list[Page], path: Path, *, site_title: str, description: str) -> None:
    """Write an llms.txt-style index pointing at the per-page files."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [f"# {site_title}", "", f"> {description}", "", "## Pages", ""]
    for page in pages:
        if not page.relative_path:
            continue
        summary = _summary(page.markdown)
        suffix = f": {summary}" if summary else ""
        lines.append(f"- [{page.title}]({page.relative_path}){suffix}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(result: CrawlResult, path: Path) -> None:
    """Write a machine-readable manifest of every page + crawl stats."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": result.profile.model_dump(),
        "stats": result.stats.model_dump(mode="json"),
        "errors": result.errors,
        "pages": [
            {
                "url": p.url,
                "canonical_url": p.canonical_url,
                "title": p.title,
                "breadcrumbs": p.breadcrumbs,
                "depth": p.depth,
                "fetcher_used": p.fetcher_used,
                "content_hash": p.content_hash,
                "relative_path": p.relative_path,
                "fetched_at": p.fetched_at.isoformat(),
            }
            for p in result.pages
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_index(pages: list[Page], path: Path, *, site_title: str) -> None:
    """Write a top-level ``index.md`` table of contents."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [f"# {site_title}", "", f"{len(pages)} pages.", "", "## Table of Contents", ""]
    for page in pages:
        if not page.relative_path:
            continue
        lines.append(f"- [{page.title}]({page.relative_path})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _summary(markdown: str, max_len: int = 160) -> str:
    """Pull a one-line summary from the first non-heading paragraph."""

    for para in markdown.split("\n\n"):
        para = para.strip()
        if not para or para.startswith("#") or para.startswith("```"):
            continue
        single = " ".join(para.split())
        if len(single) > max_len:
            single = single[: max_len - 1].rstrip() + "..."
        return single
    return ""
