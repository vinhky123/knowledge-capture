"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def aws_html() -> str:
    return (FIXTURES_DIR / "aws_ec2_concepts.html").read_text()


@pytest.fixture
def mkdocs_html() -> str:
    return (FIXTURES_DIR / "mkdocs_page.html").read_text()


@pytest.fixture
def docusaurus_html() -> str:
    return (FIXTURES_DIR / "docusaurus_page.html").read_text()


@pytest.fixture
def sphinx_html() -> str:
    return (FIXTURES_DIR / "sphinx_rtd_page.html").read_text()


@pytest.fixture
def gitbook_html() -> str:
    return (FIXTURES_DIR / "gitbook_page.html").read_text()
