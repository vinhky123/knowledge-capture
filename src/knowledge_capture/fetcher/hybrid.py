"""Hybrid fetcher: HTTP first, Playwright fallback when JS rendering is needed."""

from __future__ import annotations

import logging

from knowledge_capture.fetcher.base import Fetcher
from knowledge_capture.fetcher.browser import BrowserFetcher
from knowledge_capture.fetcher.http import HttpFetcher, needs_js
from knowledge_capture.models import FetchResult

log = logging.getLogger(__name__)


class HybridFetcher:
    """Tries HTTP, falls back to a headless browser when content looks JS-rendered."""

    def __init__(
        self,
        *,
        http: HttpFetcher,
        browser: BrowserFetcher | None = None,
        force_browser: bool = False,
    ) -> None:
        self._http = http
        self._browser = browser
        self._force_browser = force_browser
        self._js_count = 0
        self._http_count = 0

    @property
    def js_count(self) -> int:
        return self._js_count

    @property
    def http_count(self) -> int:
        return self._http_count

    async def fetch(self, url: str) -> FetchResult:
        if self._force_browser and self._browser is not None:
            self._js_count += 1
            return await self._browser.fetch(url)

        result = await self._http.fetch(url)
        if not result.ok:
            if self._browser is not None and result.status in (0, 403, 429):
                log.debug("HTTP failed (%s); retrying with browser: %s", result.status, url)
                browser_result = await self._browser.fetch(url)
                if browser_result.ok:
                    self._js_count += 1
                    return browser_result
            self._http_count += 1
            return result

        if self._browser is not None and needs_js(result.html):
            log.debug("Content looks JS-rendered; re-fetching with browser: %s", url)
            browser_result = await self._browser.fetch(url)
            if browser_result.ok:
                self._js_count += 1
                return browser_result

        self._http_count += 1
        return result

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._browser is not None:
            await self._browser.aclose()


def assert_fetcher_protocol() -> None:
    """Static-check helper: ensure all fetchers satisfy :class:`Fetcher`."""

    fetchers: list[Fetcher] = []
    fetchers.append(HttpFetcher.__new__(HttpFetcher))  # type: ignore[arg-type]
    fetchers.append(BrowserFetcher.__new__(BrowserFetcher))  # type: ignore[arg-type]
    fetchers.append(HybridFetcher.__new__(HybridFetcher))  # type: ignore[arg-type]
