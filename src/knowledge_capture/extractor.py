"""Extract the main content of a documentation page."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup, Tag

from knowledge_capture.models import SiteProfile

log = logging.getLogger(__name__)


@dataclass
class ExtractedDoc:
    """Result of extracting the main content from an HTML page."""

    title: str
    breadcrumbs: list[str]
    content_html: str
    """Cleaned HTML fragment of the main content."""
    outlinks: list[str] = field(default_factory=list)
    canonical_url: str | None = None
    """``<link rel="canonical">`` if present."""


def _select_first(soup: BeautifulSoup | Tag, selector: str) -> Tag | None:
    """Select the first element matching ``selector``.

    Accepts comma-separated selectors and returns whichever matches first.
    """

    for piece in (s.strip() for s in selector.split(",")):
        if not piece:
            continue
        try:
            match = soup.select_one(piece)
        except Exception:
            continue
        if match is not None:
            return match
    return None


def _strip(soup: Tag, selectors: list[str]) -> None:
    for sel in selectors:
        for node in soup.select(sel):
            node.decompose()


def _trafilatura_fallback(html: str, url: str) -> str | None:
    """Use trafilatura when selector-based extraction fails."""

    try:
        import trafilatura
    except ImportError:  # pragma: no cover - optional dep
        return None

    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="html",
        include_links=True,
        include_tables=True,
        include_images=True,
        favor_recall=True,
    )
    if extracted:
        return extracted
    return None


def _extract_title(content: Tag, soup: BeautifulSoup, profile_selector: str | None) -> str:
    if profile_selector:
        node = _select_first(soup, profile_selector)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    h1 = content.find("h1")
    if isinstance(h1, Tag) and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "(untitled)"


def _extract_breadcrumbs(soup: BeautifulSoup, selector: str | None) -> list[str]:
    candidates: list[Tag] = []
    if selector:
        node = _select_first(soup, selector)
        if node:
            candidates.append(node)
    candidates.extend(soup.select('[itemtype*="BreadcrumbList"]'))
    candidates.extend(soup.select("nav.breadcrumb, .breadcrumbs, .breadcrumb"))

    seen: set[str] = set()
    crumbs: list[str] = []
    for node in candidates:
        for item in node.select("li, span[itemprop='name'], a"):
            text = item.get_text(strip=True)
            if text and text not in seen:
                seen.add(text)
                crumbs.append(text)
        if crumbs:
            return crumbs
    return crumbs


def _extract_outlinks(content: Tag, base_url: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for a in content.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        absolute, _ = urldefrag(absolute)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def _extract_canonical(soup: BeautifulSoup, base_url: str) -> str | None:
    link = soup.find("link", rel="canonical")
    if isinstance(link, Tag) and link.get("href"):
        return urljoin(base_url, str(link["href"]))
    return None


def extract_content(html: str, url: str, profile: SiteProfile) -> ExtractedDoc:
    """Apply ``profile`` to ``html`` and return the cleaned main content."""

    soup = BeautifulSoup(html, "lxml")

    breadcrumbs = _extract_breadcrumbs(soup, profile.breadcrumb_selector)
    canonical = _extract_canonical(soup, url)

    _strip(soup, ["script", "style", "noscript", "template"])
    _strip(soup, profile.strip_selectors)

    content = _select_first(soup, profile.content_selector)

    if content is None:
        log.debug("Profile selector %r missed; using trafilatura fallback for %s",
                  profile.content_selector, url)
        fallback_html = _trafilatura_fallback(html, url)
        if fallback_html:
            content = BeautifulSoup(fallback_html, "lxml")

    if content is None:
        content = soup.body or soup

    title = _extract_title(content if isinstance(content, Tag) else soup,
                           soup, profile.title_selector)
    outlinks = _extract_outlinks(content if isinstance(content, Tag) else soup, url)

    content_html = (
        content.decode() if isinstance(content, (BeautifulSoup, Tag)) else str(content)
    )

    return ExtractedDoc(
        title=title,
        breadcrumbs=breadcrumbs,
        content_html=content_html,
        outlinks=outlinks,
        canonical_url=canonical or url,
    )
