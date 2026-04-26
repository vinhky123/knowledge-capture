"""Simple disk-backed HTTP response cache.

Persists raw HTML, status, headers, and validators (ETag, Last-Modified) so
subsequent runs can revalidate cheaply with conditional requests.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import diskcache


def _key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


@dataclass
class CachedResponse:
    """A previously-fetched HTTP response."""

    url: str
    final_url: str
    status: int
    html: str
    headers: dict[str, str] = field(default_factory=dict)
    js_used: bool = False

    @property
    def etag(self) -> str | None:
        return self.headers.get("etag") or self.headers.get("ETag")

    @property
    def last_modified(self) -> str | None:
        return self.headers.get("last-modified") or self.headers.get("Last-Modified")


class HttpCache:
    """Disk-backed cache for HTTP responses."""

    def __init__(self, cache_dir: Path | str, *, ttl: int | None = None) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = diskcache.Cache(str(self._cache_dir))
        self._ttl = ttl

    def get(self, url: str) -> CachedResponse | None:
        raw = self._cache.get(_key(url))
        if not raw:
            return None
        try:
            return CachedResponse(**raw)  # type: ignore[arg-type]
        except TypeError:
            return None

    def put(self, response: CachedResponse, *, ttl: int | None = None) -> None:
        payload: dict[str, Any] = asdict(response)
        self._cache.set(_key(response.url), payload, expire=ttl or self._ttl)

    def close(self) -> None:
        self._cache.close()

    def __enter__(self) -> HttpCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
