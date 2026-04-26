"""Test the writer outputs: per-page md, bundle, llms.txt, manifest, index."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from knowledge_capture.models import CrawlResult, CrawlStats, Page, SiteProfile
from knowledge_capture.writer import (
    write_bundle,
    write_index,
    write_llms_txt,
    write_manifest,
    write_pages,
)


def _make_pages() -> list[Page]:
    return [
        Page(
            url="https://docs.example.com/intro",
            canonical_url="https://docs.example.com/intro",
            title="Intro",
            markdown="# Intro\n\nIntro paragraph one.\n\nIntro paragraph two.\n",
            relative_path="docs.example.com/intro.md",
            content_hash="aaaa",
            fetched_at=datetime(2026, 1, 1),
        ),
        Page(
            url="https://docs.example.com/install",
            canonical_url="https://docs.example.com/install",
            title="Install",
            markdown="# Install\n\nInstall instructions.\n",
            relative_path="docs.example.com/install.md",
            content_hash="bbbb",
            fetched_at=datetime(2026, 1, 1),
        ),
    ]


def test_write_pages_creates_files(tmp_path: Path) -> None:
    pages = _make_pages()
    write_pages(pages, tmp_path, site_name="example")
    intro = tmp_path / "docs.example.com" / "intro.md"
    install = tmp_path / "docs.example.com" / "install.md"
    assert intro.exists()
    assert install.exists()
    assert intro.read_text().startswith("---\n")


def test_write_bundle(tmp_path: Path) -> None:
    pages = _make_pages()
    bundle = tmp_path / "bundle.md"
    write_bundle(pages, bundle, site_title="Example Docs")
    text = bundle.read_text()
    assert "Example Docs" in text
    assert "Intro" in text
    assert "Install" in text
    assert "---" in text


def test_write_llms_txt(tmp_path: Path) -> None:
    pages = _make_pages()
    path = tmp_path / "llms.txt"
    write_llms_txt(pages, path, site_title="Example Docs", description="Captured from example.com")
    text = path.read_text()
    assert "# Example Docs" in text
    assert "[Intro](docs.example.com/intro.md)" in text
    assert "[Install](docs.example.com/install.md)" in text


def test_write_manifest(tmp_path: Path) -> None:
    profile = SiteProfile(name="aws-docs", content_selector="main")
    result = CrawlResult(profile=profile, pages=_make_pages(), stats=CrawlStats())
    path = tmp_path / "manifest.json"
    write_manifest(result, path)
    payload = json.loads(path.read_text())
    assert payload["profile"]["name"] == "aws-docs"
    assert len(payload["pages"]) == 2


def test_write_index(tmp_path: Path) -> None:
    pages = _make_pages()
    path = tmp_path / "index.md"
    write_index(pages, path, site_title="Example Docs")
    text = path.read_text()
    assert "Example Docs" in text
    assert "[Intro](docs.example.com/intro.md)" in text
