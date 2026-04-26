"""HTTP fetcher built on httpx with retries, caching, and per-host rate limiting."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from urllib.parse import urlparse

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from knowledge_capture.cache import CachedResponse, HttpCache
from knowledge_capture.models import FetchResult

log = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}

_JS_HINTS = (
    "__NEXT_DATA__",
    "__NUXT__",
    "window.__INITIAL_STATE__",
    "window.__APOLLO_STATE__",
    "ng-version=",
    "data-reactroot",
)


class TokenBucket:
    """Per-host token bucket for soft rate limiting."""

    def __init__(self, rate_per_sec: float, capacity: float | None = None) -> None:
        self.rate = max(rate_per_sec, 0.001)
        self.capacity = capacity if capacity is not None else max(rate_per_sec, 1.0)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def take(self, amount: float = 1.0) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                deficit = amount - self._tokens
                await asyncio.sleep(deficit / self.rate)


class HttpFetcher:
    """Async HTTP fetcher with cache, retries, and per-host rate limiting."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 30.0,
        rate_limit_rps: float = 4.0,
        cache: HttpCache | None = None,
        max_retries: int = 3,
        follow_redirects: bool = True,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            http2=True,
        )
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(rate_limit_rps)
        )
        self._rate = rate_limit_rps
        self._cache = cache
        self._max_retries = max_retries

    async def fetch(self, url: str) -> FetchResult:
        host = urlparse(url).netloc
        await self._buckets[host].take()

        cached = self._cache.get(url) if self._cache else None
        request_headers: dict[str, str] = {}
        if cached:
            if cached.etag:
                request_headers["If-None-Match"] = cached.etag
            if cached.last_modified:
                request_headers["If-Modified-Since"] = cached.last_modified

        try:
            resp = await self._with_retries(url, request_headers)
        except RetryError as exc:
            return FetchResult(
                url=url,
                final_url=url,
                status=0,
                html="",
                error=f"retries exhausted: {exc}",
            )
        except httpx.HTTPError as exc:
            return FetchResult(
                url=url, final_url=url, status=0, html="", error=str(exc)
            )

        if resp.status_code == 304 and cached:
            log.debug("304 for %s, using cached body", url)
            return FetchResult(
                url=url,
                final_url=cached.final_url,
                status=200,
                html=cached.html,
                headers=cached.headers,
                from_cache=True,
            )

        html = resp.text
        result = FetchResult(
            url=url,
            final_url=str(resp.url),
            status=resp.status_code,
            html=html,
            headers=dict(resp.headers),
        )

        if result.ok and self._cache is not None:
            self._cache.put(
                CachedResponse(
                    url=url,
                    final_url=str(resp.url),
                    status=resp.status_code,
                    html=html,
                    headers=dict(resp.headers),
                )
            )
        return result

    async def _with_retries(self, url: str, extra_headers: dict[str, str]) -> httpx.Response:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(httpx.TransportError),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.get(url, headers=extra_headers)
                if resp.status_code in _RETRYABLE_STATUSES:
                    raise httpx.TransportError(f"retryable status {resp.status_code}")
                return resp
        raise RuntimeError("unreachable")  # pragma: no cover

    async def aclose(self) -> None:
        await self._client.aclose()


_TEXT_DENSITY_RE = re.compile(r"\s+")


def text_length(html: str) -> int:
    """Rough text-length estimate without parsing the full DOM."""
    no_tags = re.sub(r"<[^>]+>", " ", html)
    return len(_TEXT_DENSITY_RE.sub(" ", no_tags).strip())


def needs_js(html: str, *, min_text_length: int = 400) -> bool:
    """Heuristic: does this HTML look like it requires JS to render content?"""

    if not html:
        return True
    body_len = text_length(html)
    if body_len < min_text_length and any(hint in html for hint in _JS_HINTS):
        return True
    if "<noscript>" in html and body_len < min_text_length:
        return True
    return body_len < 80
