"""Test extractor + converter on each known profile fixture."""

from __future__ import annotations

import pytest

from knowledge_capture.converter import html_to_markdown
from knowledge_capture.detector.profiles import match_known_profile
from knowledge_capture.extractor import extract_content


@pytest.mark.parametrize(
    "fixture_name, url, must_contain, must_not_contain",
    [
        (
            "aws_html",
            "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html",
            ["What is Amazon EC2?", "Features", "aws ec2 run-instances"],
            ["AWS site header", "Was this helpful?", "AWS footer"],
        ),
        (
            "mkdocs_html",
            "https://example.com/getting-started/",
            ["Getting Started", "pip install my-tool"],
            ["site header", "site footer", "View source on GitHub"],
        ),
        (
            "docusaurus_html",
            "https://example.com/docs/intro",
            ["Tutorial Intro", "Prerequisites", "create-docusaurus"],
            ["site navbar", "Copyright", "prev/next"],
        ),
        (
            "sphinx_html",
            "https://example.readthedocs.io/quickstart.html",
            ["Quickstart", "pip install rtd-project"],
            ["search"],
        ),
        (
            "gitbook_html",
            "https://example.gitbook.io/introduction",
            ["Introduction", "Welcome to my book"],
            [],
        ),
    ],
)
def test_extract_and_convert(
    request: pytest.FixtureRequest,
    fixture_name: str,
    url: str,
    must_contain: list[str],
    must_not_contain: list[str],
) -> None:
    html = request.getfixturevalue(fixture_name)
    profile = match_known_profile(html, url)
    assert profile is not None, f"Expected to match a profile for {fixture_name}"

    extracted = extract_content(html, url, profile)
    assert extracted.title

    md = html_to_markdown(extracted.content_html, base_url=url)

    for needle in must_contain:
        assert needle in md, f"Expected {needle!r} in markdown:\n{md}"
    for needle in must_not_contain:
        assert needle not in md, f"Did not expect {needle!r} in markdown:\n{md}"


def test_aws_breadcrumbs_and_outlinks(aws_html: str) -> None:
    url = "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html"
    profile = match_known_profile(aws_html, url)
    assert profile is not None
    extracted = extract_content(aws_html, url, profile)

    assert extracted.title == "What is Amazon EC2?"
    assert any("Concepts" in c for c in extracted.breadcrumbs)
    assert "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Instances.html" in extracted.outlinks
    assert "https://aws.amazon.com/ec2/" in extracted.outlinks
    assert extracted.canonical_url == url


def test_code_block_language_preserved(aws_html: str) -> None:
    url = "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html"
    profile = match_known_profile(aws_html, url)
    assert profile is not None
    extracted = extract_content(aws_html, url, profile)
    md = html_to_markdown(extracted.content_html, base_url=url)
    assert "```bash" in md
    assert "aws ec2 run-instances" in md
