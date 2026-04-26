"""Tests for postprocess: frontmatter, link rewriting, dedupe, heading normalization."""

from __future__ import annotations

from datetime import datetime

from knowledge_capture.models import Page
from knowledge_capture.postprocess import (
    add_frontmatter,
    dedupe_pages,
    normalize_headings,
    rewrite_links,
)


def _page(url: str, *, markdown: str = "", relative_path: str = "", content_hash: str = "") -> Page:
    return Page(
        url=url,
        canonical_url=url,
        title=f"Page {url}",
        markdown=markdown,
        relative_path=relative_path,
        content_hash=content_hash,
        fetched_at=datetime(2026, 1, 1, 0, 0, 0),
    )


def test_add_frontmatter_emits_yaml() -> None:
    page = _page("https://example.com/foo", markdown="hello\n", content_hash="abc123")
    out = add_frontmatter(page, site_name="example")
    assert out.startswith("---\n")
    assert "title: 'Page https://example.com/foo'" in out or "title: Page https://example.com/foo" in out
    assert "source_url: https://example.com/foo" in out
    assert "site: example" in out
    assert "content_hash: abc123" in out
    assert "hello" in out


def test_rewrite_links_to_relative() -> None:
    here = _page(
        "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html",
        relative_path="docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.md",
        markdown=(
            "See [Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Instances.html) "
            "and [external](https://aws.amazon.com/ec2/)."
        ),
    )
    url_to_path = {
        "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html": here.relative_path,
        "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Instances.html":
            "docs.aws.amazon.com/AWSEC2/latest/UserGuide/Instances.md",
    }
    out = rewrite_links(here.markdown, here, url_to_path)
    assert "Instances.md" in out
    assert "https://aws.amazon.com/ec2/" in out


def test_dedupe_drops_duplicate_hashes() -> None:
    a = _page("https://x.com/a", markdown="x", content_hash="h1")
    b = _page("https://x.com/b", markdown="x", content_hash="h1")
    c = _page("https://x.com/c", markdown="y", content_hash="h2")
    kept, dropped = dedupe_pages([a, b, c])
    assert dropped == 1
    assert {p.url for p in kept} == {"https://x.com/a", "https://x.com/c"}


def test_normalize_headings_demotes_extra_h1() -> None:
    md = "# Title\n\n# Other\n\n## Sub\n"
    out = normalize_headings(md)
    assert out.count("# Title") == 1
    assert out.count("## Other") == 1
    assert out.count("## Sub") == 1
