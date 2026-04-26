"""Generic, profile-agnostic content + nav detection."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from knowledge_capture.detector.profiles import GENERIC_PROFILE
from knowledge_capture.models import SiteProfile

log = logging.getLogger(__name__)

_CONTENT_CANDIDATES: tuple[str, ...] = (
    "main",
    "[role='main']",
    "article",
    "#main-content",
    "#main",
    "#content",
    ".content",
    ".documentation",
    ".doc-content",
    ".markdown-body",
)

_NAV_CANDIDATES: tuple[str, ...] = (
    "nav.toc",
    "nav.sidebar",
    "aside.sidebar",
    "[role='navigation']",
    "nav",
    ".sidebar",
    ".toc",
)


def _text_length(node: Tag) -> int:
    return len(node.get_text(" ", strip=True))


def _score_nav(node: Tag, base_host: str, base_prefix: str) -> int:
    """Higher score = more likely the doc nav."""

    score = 0
    for a in node.find_all("a", href=True):
        href = str(a["href"])
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != base_host:
            score -= 1
            continue
        path = parsed.path or href
        if path.startswith(base_prefix):
            score += 3
        else:
            score += 1
    return score


def detect_profile(html: str, url: str) -> SiteProfile:
    """Best-effort generic detection of the main content + nav selectors."""

    soup = BeautifulSoup(html, "lxml")
    parsed = urlparse(url)
    base_host = parsed.netloc
    base_prefix = parsed.path.rsplit("/", 1)[0] + "/"

    best_content_sel: str | None = None
    best_content_len = 0
    for sel in _CONTENT_CANDIDATES:
        node = soup.select_one(sel)
        if isinstance(node, Tag):
            length = _text_length(node)
            if length > best_content_len:
                best_content_len = length
                best_content_sel = sel

    nav_selectors: list[str] = []
    best_nav_score = 0
    best_nav_sel: str | None = None
    for sel in _NAV_CANDIDATES:
        for node in soup.select(sel):
            if not isinstance(node, Tag):
                continue
            score = _score_nav(node, base_host, base_prefix)
            if score > best_nav_score:
                best_nav_score = score
                best_nav_sel = sel
    if best_nav_sel:
        nav_selectors.append(best_nav_sel)

    if not best_content_sel:
        log.debug("Heuristic detection fell back to generic profile for %s", url)
        return GENERIC_PROFILE

    confidence = min(1.0, 0.4 + best_content_len / 4000.0)
    return SiteProfile(
        name="heuristic",
        content_selector=best_content_sel,
        nav_selectors=nav_selectors or list(GENERIC_PROFILE.nav_selectors),
        strip_selectors=list(GENERIC_PROFILE.strip_selectors),
        confidence=confidence,
    )
