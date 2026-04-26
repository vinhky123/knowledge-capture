"""Tests for CrawlConfig validation."""

from __future__ import annotations

import pytest

from knowledge_capture.config import CrawlConfig


def test_seed_url_must_be_http() -> None:
    with pytest.raises(ValueError):
        CrawlConfig(seed_url="ftp://example.com/foo")


def test_url_prefix_strips_filename() -> None:
    cfg = CrawlConfig(seed_url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html")
    assert cfg.url_prefix == "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/"


def test_url_prefix_keeps_trailing_slash() -> None:
    cfg = CrawlConfig(seed_url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/")
    assert cfg.url_prefix == "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/"


def test_positive_int_validation() -> None:
    with pytest.raises(ValueError):
        CrawlConfig(seed_url="https://example.com/", max_pages=0)
