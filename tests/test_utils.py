"""Tests for URL canonicalization and path mapping helpers."""

from __future__ import annotations

import pytest

from knowledge_capture.utils import canonicalize_url, url_to_relative_path


def test_canonicalize_strips_fragment_and_tracking() -> None:
    url = "https://Docs.Example.com/foo?utm_source=x&id=42#section-2"
    assert canonicalize_url(url) == "https://docs.example.com/foo?id=42"


def test_canonicalize_strips_index_html() -> None:
    assert (
        canonicalize_url("https://x.com/AWSEC2/latest/UserGuide/index.html")
        == "https://x.com/AWSEC2/latest/UserGuide/"
    )


def test_canonicalize_sorts_query() -> None:
    a = canonicalize_url("https://x.com/page?b=2&a=1")
    b = canonicalize_url("https://x.com/page?a=1&b=2")
    assert a == b


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html",
            "docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.md",
        ),
        (
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/",
            "docs.aws.amazon.com/AWSEC2/latest/UserGuide/index.md",
        ),
        (
            "https://example.com/",
            "example.com/index.md",
        ),
    ],
)
def test_url_to_relative_path(url: str, expected: str) -> None:
    assert url_to_relative_path(url) == expected
