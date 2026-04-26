"""Domain models shared across the pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SiteProfile(BaseModel):
    """How to extract content from a particular documentation site."""

    model_config = ConfigDict(extra="forbid")

    name: str
    """Human-readable identifier (e.g. ``"aws-docs"``, ``"mkdocs"``)."""

    content_selector: str
    """CSS selector for the main content container.

    May be a comma-separated list; the first match wins.
    """

    nav_selectors: list[str] = Field(default_factory=list)
    """CSS selectors for navigation/TOC blocks used to discover URLs."""

    strip_selectors: list[str] = Field(default_factory=list)
    """CSS selectors for elements removed before extraction (nav, footer, ads, ...)."""

    breadcrumb_selector: str | None = None
    """CSS selector for breadcrumb container (optional)."""

    title_selector: str | None = None
    """CSS selector for the page title; falls back to ``<h1>`` then ``<title>``."""

    requires_js: bool = False
    """If True, ``HybridFetcher`` will skip the HTTP attempt and go straight to Playwright."""

    confidence: float = 1.0
    """0..1 score; used when comparing detector results."""


class FetchResult(BaseModel):
    """Result of fetching a single URL."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str
    final_url: str
    status: int
    html: str
    headers: dict[str, str] = Field(default_factory=dict)
    js_used: bool = False
    from_cache: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 400 and bool(self.html)


class Page(BaseModel):
    """A captured documentation page after extraction + conversion."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str
    canonical_url: str
    title: str
    breadcrumbs: list[str] = Field(default_factory=list)
    html: str = ""
    """Cleaned HTML fragment of the main content (post-extract, pre-conversion)."""

    markdown: str = ""
    """Final markdown body (without frontmatter)."""

    outlinks: list[str] = Field(default_factory=list)
    depth: int = 0
    fetched_at: datetime = Field(default_factory=_utcnow)
    fetcher_used: str = "http"
    content_hash: str = ""
    """Stable hash of the markdown body, used for dedupe."""

    relative_path: str = ""
    """Path relative to ``output_dir`` (e.g. ``docs.aws.amazon.com/.../concepts.md``)."""

    extra: dict[str, Any] = Field(default_factory=dict)


class CrawlStats(BaseModel):
    """Aggregate statistics for a crawl run."""

    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    pages_fetched: int = 0
    pages_written: int = 0
    pages_skipped: int = 0
    pages_failed: int = 0
    js_fetches: int = 0
    bytes_downloaded: int = 0
    duplicates_dropped: int = 0


class CrawlResult(BaseModel):
    """Output of a crawl run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    profile: SiteProfile
    pages: list[Page] = Field(default_factory=list)
    stats: CrawlStats = Field(default_factory=CrawlStats)
    errors: list[str] = Field(default_factory=list)
