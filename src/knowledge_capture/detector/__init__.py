"""Detect documentation site patterns (profiles, sitemaps, heuristics, LLM)."""

from __future__ import annotations

from knowledge_capture.detector.profiles import (
    GENERIC_PROFILE,
    KNOWN_PROFILES,
    match_known_profile,
)
from knowledge_capture.detector.sitemap import discover_sitemaps, parse_sitemap

__all__ = [
    "GENERIC_PROFILE",
    "KNOWN_PROFILES",
    "discover_sitemaps",
    "match_known_profile",
    "parse_sitemap",
]
