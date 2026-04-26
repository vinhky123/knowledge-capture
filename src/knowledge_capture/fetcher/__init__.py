"""Page fetcher implementations."""

from __future__ import annotations

from knowledge_capture.fetcher.base import Fetcher
from knowledge_capture.fetcher.http import HttpFetcher
from knowledge_capture.fetcher.hybrid import HybridFetcher

__all__ = ["Fetcher", "HttpFetcher", "HybridFetcher"]
