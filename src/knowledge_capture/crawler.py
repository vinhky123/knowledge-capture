"""Async BFS crawler that orchestrates fetch -> extract -> convert."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from urllib.parse import urlparse

from knowledge_capture.config import CrawlConfig
from knowledge_capture.converter import html_to_markdown
from knowledge_capture.extractor import extract_content
from knowledge_capture.fetcher.base import Fetcher
from knowledge_capture.models import CrawlResult, CrawlStats, Page, SiteProfile
from knowledge_capture.robots import RobotsChecker
from knowledge_capture.utils import canonicalize_url, short_hash, url_to_relative_path

log = logging.getLogger(__name__)


ProgressCallback = Callable[[Page], None]


class Crawler:
    """Async BFS crawler with scope filtering and per-host rate limiting."""

    def __init__(
        self,
        config: CrawlConfig,
        fetcher: Fetcher,
        profile: SiteProfile,
        *,
        robots: RobotsChecker | None = None,
        seed_urls: Iterable[str] | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.fetcher = fetcher
        self.profile = profile
        self.robots = robots
        self._extra_seeds = list(seed_urls or [])
        self._progress = progress

        self._include = [re.compile(p) for p in config.include_patterns]
        self._exclude = [re.compile(p) for p in config.exclude_patterns]

        self._queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._enqueued: set[str] = set()
        self._results: dict[str, Page] = {}
        self._errors: list[str] = []
        self._stats = CrawlStats()

    def in_scope(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        if self.config.scope == "domain":
            if parsed.netloc != self.config.base_host:
                return False
        elif self.config.scope == "prefix" and not url.startswith(self.config.url_prefix):
            return False

        if self._exclude and any(p.search(url) for p in self._exclude):
            return False
        if self._include and not any(p.search(url) for p in self._include):
            return False

        if (
            self.config.obey_robots
            and self.robots is not None
            and not self.robots.can_fetch(url)
        ):
            return False

        return True

    def _seed_initial(self) -> None:
        seeds = [self.config.seed_url, *self._extra_seeds]
        for url in seeds:
            canonical = canonicalize_url(url)
            if canonical in self._enqueued:
                continue
            if not self.in_scope(canonical):
                continue
            self._enqueued.add(canonical)
            self._queue.put_nowait((canonical, 0))

    async def run(self) -> CrawlResult:
        self._stats = CrawlStats()
        self._seed_initial()

        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.config.concurrency)
        ]
        await self._queue.join()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        self._stats.finished_at = datetime.now(UTC)
        ordered = sorted(
            self._results.values(),
            key=lambda p: (p.depth, p.url),
        )
        return CrawlResult(
            profile=self.profile,
            pages=ordered,
            stats=self._stats,
            errors=list(self._errors),
        )

    async def _worker(self, wid: int) -> None:
        while True:
            try:
                url, depth = await self._queue.get()
            except asyncio.CancelledError:
                return
            try:
                await self._process(url, depth)
            except Exception as exc:
                log.exception("Worker %d crashed on %s", wid, url)
                self._errors.append(f"{url}: {exc}")
                self._stats.pages_failed += 1
            finally:
                self._queue.task_done()

    async def _process(self, url: str, depth: int) -> None:
        if len(self._results) >= self.config.max_pages:
            return
        if depth > self.config.max_depth:
            return

        result = await self.fetcher.fetch(url)
        if not result.ok:
            log.warning("Failed to fetch %s (status=%s, error=%s)",
                        url, result.status, result.error)
            self._errors.append(f"{url}: status={result.status} error={result.error}")
            self._stats.pages_failed += 1
            return

        self._stats.pages_fetched += 1
        if result.js_used:
            self._stats.js_fetches += 1
        self._stats.bytes_downloaded += len(result.html)

        try:
            extracted = extract_content(result.html, result.final_url, self.profile)
        except Exception as exc:
            log.warning("Extraction failed for %s: %s", url, exc)
            self._errors.append(f"{url}: extract error {exc}")
            self._stats.pages_failed += 1
            return

        markdown = html_to_markdown(extracted.content_html, base_url=result.final_url)
        canonical = canonicalize_url(extracted.canonical_url or result.final_url or url)
        relative_path = url_to_relative_path(canonical)

        page = Page(
            url=url,
            canonical_url=canonical,
            title=extracted.title,
            breadcrumbs=extracted.breadcrumbs,
            html=extracted.content_html,
            markdown=markdown,
            outlinks=extracted.outlinks,
            depth=depth,
            fetcher_used="browser" if result.js_used else "http",
            content_hash=short_hash(markdown, n=16),
            relative_path=relative_path,
        )
        self._results[canonical] = page

        if self._progress is not None:
            with contextlib.suppress(Exception):
                self._progress(page)

        for link in extracted.outlinks:
            canonical_link = canonicalize_url(link)
            if canonical_link in self._enqueued:
                continue
            if not self.in_scope(canonical_link):
                continue
            self._enqueued.add(canonical_link)
            await self._queue.put((canonical_link, depth + 1))
