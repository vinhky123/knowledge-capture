"""Fetcher protocol shared by HTTP and browser implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from knowledge_capture.models import FetchResult


@runtime_checkable
class Fetcher(Protocol):
    """Anything that can asynchronously fetch a URL and return a :class:`FetchResult`."""

    async def fetch(self, url: str) -> FetchResult: ...

    async def aclose(self) -> None: ...
