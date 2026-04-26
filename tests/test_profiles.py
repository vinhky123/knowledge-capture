"""Test that known site profiles match their corresponding fixtures."""

from __future__ import annotations

from knowledge_capture.detector.profiles import match_known_profile


def test_aws_profile_matches(aws_html: str) -> None:
    profile = match_known_profile(
        aws_html, "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html"
    )
    assert profile is not None
    assert profile.name == "aws-docs"


def test_mkdocs_profile_matches(mkdocs_html: str) -> None:
    profile = match_known_profile(mkdocs_html, "https://example.com/")
    assert profile is not None
    assert profile.name == "mkdocs"


def test_docusaurus_profile_matches(docusaurus_html: str) -> None:
    profile = match_known_profile(docusaurus_html, "https://example.com/docs/intro")
    assert profile is not None
    assert profile.name == "docusaurus"


def test_sphinx_profile_matches(sphinx_html: str) -> None:
    profile = match_known_profile(sphinx_html, "https://example.readthedocs.io/quickstart.html")
    assert profile is not None
    assert profile.name == "sphinx-rtd"


def test_gitbook_profile_matches(gitbook_html: str) -> None:
    profile = match_known_profile(gitbook_html, "https://example.gitbook.io/introduction")
    assert profile is not None
    assert profile.name == "gitbook"


def test_unknown_site_returns_none() -> None:
    html = "<html><body><h1>Hello</h1></body></html>"
    assert match_known_profile(html, "https://example.com") is None
