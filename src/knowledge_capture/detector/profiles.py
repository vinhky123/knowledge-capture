"""Built-in site profiles for common documentation engines."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from knowledge_capture.models import SiteProfile


@dataclass(frozen=True)
class ProfileMatcher:
    """A heuristic that detects a particular doc-engine profile."""

    profile: SiteProfile
    url_patterns: tuple[re.Pattern[str], ...] = ()
    """Regexes against the full URL (host included)."""
    meta_generators: tuple[re.Pattern[str], ...] = ()
    """Regexes against the value of ``<meta name="generator">``."""
    body_classes: tuple[str, ...] = ()
    body_selectors: tuple[str, ...] = ()
    """Selectors that, if present, indicate this profile."""
    custom: Callable[[BeautifulSoup, str], bool] | None = None

    def matches(self, soup: BeautifulSoup, url: str) -> bool:
        if any(p.search(url) for p in self.url_patterns):
            return True
        if self.meta_generators:
            meta = soup.find("meta", attrs={"name": "generator"})
            if meta and meta.get("content"):
                content = str(meta["content"])
                if any(p.search(content) for p in self.meta_generators):
                    return True
        if self.body_classes:
            body = soup.body
            if body is not None:
                classes = set(body.get("class") or [])
                if any(c in classes for c in self.body_classes):
                    return True
        for sel in self.body_selectors:
            try:
                if soup.select_one(sel) is not None:
                    return True
            except Exception:
                continue
        return bool(self.custom is not None and self.custom(soup, url))


# --- Profiles -----------------------------------------------------------------

AWS_DOCS = SiteProfile(
    name="aws-docs",
    content_selector="#main-content, #main-col-body, main#main-content",
    nav_selectors=["#awsdocs-toc, nav#awsdocs-toc, #toc"],
    strip_selectors=[
        "header", "footer", "nav",
        "#awsdocs-page-header",
        "#awsdocs-toc",
        ".awsdocs-feedback-container",
        ".feedback-container",
        ".awsui-help-panel",
        ".breadcrumb",
        "#awsdocs-language-selector",
    ],
    breadcrumb_selector="#breadcrumbs, .breadcrumb",
    requires_js=False,
)

MKDOCS = SiteProfile(
    name="mkdocs",
    content_selector="article.md-content__inner, article, .md-content",
    nav_selectors=[".md-nav, nav.md-nav"],
    strip_selectors=[
        "header.md-header", "footer.md-footer", ".md-sidebar",
        ".md-source-file", ".md-feedback",
    ],
    requires_js=False,
)

DOCUSAURUS = SiteProfile(
    name="docusaurus",
    content_selector="article, main article, .theme-doc-markdown",
    nav_selectors=[".theme-doc-sidebar-menu, nav.menu"],
    strip_selectors=[
        "nav.navbar", "footer", ".theme-doc-toc-mobile",
        ".theme-edit-this-page", ".pagination-nav",
    ],
    requires_js=False,
)

SPHINX_RTD = SiteProfile(
    name="sphinx-rtd",
    content_selector="div[role='main'], .rst-content .document, .document",
    nav_selectors=[".wy-menu-vertical, nav.wy-nav-side"],
    strip_selectors=[
        "nav.wy-nav-side", ".wy-side-nav-search", "footer",
        ".rst-versions", ".rst-footer-buttons",
    ],
    requires_js=False,
)

GITBOOK = SiteProfile(
    name="gitbook",
    content_selector=".page-inner, .markdown-section, main",
    nav_selectors=[".book-summary, nav[aria-label='Table of Contents']"],
    strip_selectors=[".book-summary", ".book-header", ".book-actions"],
    requires_js=False,
)

GENERIC_PROFILE = SiteProfile(
    name="generic",
    content_selector="main, [role='main'], article, #content, .content, .documentation, body",
    nav_selectors=["nav, .sidebar, .toc, [role='navigation']"],
    strip_selectors=[
        "header", "footer", "nav", "aside",
        ".sidebar", ".toc", ".breadcrumb", ".breadcrumbs",
        ".navigation", ".pagination", ".feedback",
    ],
    confidence=0.4,
)


KNOWN_PROFILES: tuple[ProfileMatcher, ...] = (
    ProfileMatcher(
        profile=AWS_DOCS,
        url_patterns=(re.compile(r"docs\.aws\.amazon\.com"),),
    ),
    ProfileMatcher(
        profile=MKDOCS,
        meta_generators=(re.compile(r"mkdocs", re.IGNORECASE),),
        body_selectors=("body[data-md-color-scheme]", ".md-container"),
    ),
    ProfileMatcher(
        profile=DOCUSAURUS,
        meta_generators=(re.compile(r"docusaurus", re.IGNORECASE),),
        body_selectors=(".theme-doc-markdown", "main .docMainContainer"),
    ),
    ProfileMatcher(
        profile=SPHINX_RTD,
        meta_generators=(re.compile(r"sphinx", re.IGNORECASE),),
        body_selectors=(".wy-nav-content", ".rst-content", "div[role='main'].document"),
    ),
    ProfileMatcher(
        profile=GITBOOK,
        body_selectors=(".page-inner", ".markdown-section"),
        custom=lambda soup, url: bool(soup.find("meta", attrs={"name": "GENERATOR", "content": re.compile(r"GitBook", re.IGNORECASE)})),
    ),
)


def match_known_profile(html: str, url: str) -> SiteProfile | None:
    """Return the first known profile whose matcher fires, else ``None``."""

    soup = BeautifulSoup(html, "lxml")
    for matcher in KNOWN_PROFILES:
        if matcher.matches(soup, url):
            return matcher.profile
    return None


def host_of(url: str) -> str:
    return urlparse(url).netloc
