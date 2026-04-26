"""Post-process pages: frontmatter, link rewriting, dedupe, heading normalization."""

from __future__ import annotations

import logging
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import urldefrag, urlparse

import yaml

from knowledge_capture.models import Page
from knowledge_capture.utils import canonicalize_url

log = logging.getLogger(__name__)

_MD_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)")
_MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def add_frontmatter(page: Page, *, site_name: str | None = None) -> str:
    """Prepend a YAML frontmatter block to the markdown body."""

    body = page.markdown or ""
    meta: dict[str, object] = {
        "title": page.title,
        "source_url": page.url,
    }
    if page.canonical_url and page.canonical_url != page.url:
        meta["canonical_url"] = page.canonical_url
    if page.breadcrumbs:
        meta["breadcrumbs"] = page.breadcrumbs
    if site_name:
        meta["site"] = site_name
    if page.fetched_at:
        meta["captured_at"] = page.fetched_at.isoformat()
    if page.content_hash:
        meta["content_hash"] = page.content_hash
    if page.fetcher_used:
        meta["fetcher"] = page.fetcher_used

    yaml_block = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_block}\n---\n\n{body.strip()}\n"


def rewrite_links(markdown: str, page: Page, url_to_path: dict[str, str]) -> str:
    """Rewrite same-site URLs to relative ``.md`` links.

    ``url_to_path`` maps canonical URL -> page-relative output path.
    External URLs and anchors are preserved as-is.
    """

    if not page.relative_path:
        return markdown
    here = PurePosixPath(page.relative_path).parent

    def _resolve(target: str) -> str:
        target = target.strip()
        if not target or target.startswith(("#", "mailto:", "tel:", "javascript:")):
            return target
        absolute, fragment = urldefrag(target)
        canonical = canonicalize_url(absolute)
        rel = url_to_path.get(canonical)
        if rel is None:
            return target
        rel_path = posixpath.relpath(rel, str(here) if str(here) != "." else "")
        if fragment:
            rel_path = f"{rel_path}#{fragment}"
        return rel_path

    def _link_sub(match: re.Match[str]) -> str:
        text = match.group(1)
        href = match.group(2)
        new = _resolve(href)
        return f"[{text}]({new})"

    def _img_sub(match: re.Match[str]) -> str:
        match.group(1)
        src = match.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        return match.group(0)

    out = _MD_LINK_RE.sub(_link_sub, markdown)
    out = _MD_IMG_RE.sub(_img_sub, out)
    return out


def dedupe_pages(pages: list[Page]) -> tuple[list[Page], int]:
    """Drop pages whose ``content_hash`` was already seen. Returns (kept, dropped_count)."""

    seen: set[str] = set()
    kept: list[Page] = []
    dropped = 0
    for page in pages:
        if not page.content_hash:
            kept.append(page)
            continue
        if page.content_hash in seen:
            dropped += 1
            log.debug("Dropping duplicate %s (hash %s)", page.url, page.content_hash[:12])
            continue
        seen.add(page.content_hash)
        kept.append(page)
    return kept, dropped


def normalize_headings(markdown: str) -> str:
    """Ensure exactly one H1; demote subsequent H1s to H2.

    Also collapses runs of blank lines.
    """

    seen_h1 = False
    out_lines: list[str] = []
    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            if level == 1:
                if seen_h1:
                    line = "## " + m.group(2)
                else:
                    seen_h1 = True
        out_lines.append(line)
    text = "\n".join(out_lines)
    return _BLANK_LINES_RE.sub("\n\n", text).strip() + "\n"


def derive_site_name(seed_url: str, override: str | None = None) -> str:
    if override:
        return override
    parsed = urlparse(seed_url)
    return parsed.netloc or "documentation"
