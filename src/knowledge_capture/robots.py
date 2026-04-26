"""robots.txt handling."""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)


class RobotsChecker:
    """Tiny wrapper around ``urllib.robotparser`` with an httpx-backed fetch."""

    def __init__(self, base_url: str, user_agent: str, *, timeout: float = 10.0) -> None:
        parsed = urlparse(base_url)
        self.base = f"{parsed.scheme}://{parsed.netloc}"
        self.user_agent = user_agent
        self._parser = RobotFileParser()
        self._loaded = False
        self._sitemaps: list[str] = []
        self._timeout = timeout

    def load(self) -> None:
        """Fetch and parse robots.txt. Failures are non-fatal (assume allow)."""

        if self._loaded:
            return
        url = urljoin(self.base, "/robots.txt")
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=self._timeout,
                headers={"User-Agent": self.user_agent},
            ) as client:
                resp = client.get(url)
            if resp.status_code >= 400:
                log.debug("robots.txt fetch returned %s for %s", resp.status_code, url)
                self._parser.parse([])
            else:
                self._parser.parse(resp.text.splitlines())
                self._sitemaps = self._extract_sitemaps(resp.text)
        except Exception as exc:  # network errors are tolerated
            log.warning("Failed to fetch robots.txt at %s: %s", url, exc)
            self._parser.parse([])
        self._loaded = True

    @staticmethod
    def _extract_sitemaps(content: str) -> list[str]:
        sitemaps: list[str] = []
        for line in content.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            if key.strip().lower() == "sitemap":
                sitemaps.append(value.strip())
        return sitemaps

    def can_fetch(self, url: str) -> bool:
        if not self._loaded:
            self.load()
        try:
            return self._parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def crawl_delay(self) -> float | None:
        if not self._loaded:
            self.load()
        try:
            value = self._parser.crawl_delay(self.user_agent)
        except Exception:
            return None
        return float(value) if value is not None else None

    def sitemaps(self) -> list[str]:
        if not self._loaded:
            self.load()
        return list(self._sitemaps)
