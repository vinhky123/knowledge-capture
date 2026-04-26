"""Playwright-backed fetcher for JS-rendered docs."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from knowledge_capture.models import FetchResult

log = logging.getLogger(__name__)


class BrowserFetcher:
    """Headless-Chromium fetcher.

    Uses Playwright lazily so the dependency is optional. Construction
    always succeeds; an :class:`ImportError` (wrapped as a runtime error
    in :meth:`fetch`) is raised on first use if Playwright is missing.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 30.0,
        wait_until: str = "networkidle",
        headless: bool = True,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_ms = int(timeout * 1000)
        self._wait_until = wait_until
        self._headless = headless
        self._lock = asyncio.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    async def _ensure_started(self) -> None:
        if self._context is not None:
            return
        async with self._lock:
            if self._context is not None:
                return
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "Playwright is not installed. Install with `pip install knowledge-capture[browser]` "
                    "and run `playwright install chromium`."
                ) from exc

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            self._context = await self._browser.new_context(user_agent=self._user_agent)

    async def fetch(self, url: str) -> FetchResult:
        await self._ensure_started()
        assert self._context is not None
        page = await self._context.new_page()
        try:
            try:
                response = await page.goto(
                    url, wait_until=self._wait_until, timeout=self._timeout_ms,
                )
            except Exception as exc:
                return FetchResult(url=url, final_url=url, status=0, html="", error=str(exc))

            with contextlib.suppress(Exception):
                await page.evaluate(
                    "() => new Promise(r => { window.scrollTo(0, document.body.scrollHeight); setTimeout(r, 250); })"
                )

            try:
                html = await page.content()
            except Exception as exc:
                return FetchResult(url=url, final_url=url, status=0, html="", error=str(exc))

            status = response.status if response else 0
            final_url = page.url
            return FetchResult(
                url=url,
                final_url=final_url,
                status=status or 200,
                html=html,
                js_used=True,
            )
        finally:
            await page.close()

    async def aclose(self) -> None:
        try:
            if self._context is not None:
                await self._context.close()
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        except Exception as exc:  # pragma: no cover
            log.debug("Error closing browser: %s", exc)
        finally:
            self._context = None
            self._browser = None
            self._playwright = None
