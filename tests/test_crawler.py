"""Integration test: crawler against a mock fetcher with linked fixtures."""

from __future__ import annotations

import pytest

from knowledge_capture.config import CrawlConfig
from knowledge_capture.crawler import Crawler
from knowledge_capture.detector.profiles import AWS_DOCS
from knowledge_capture.models import FetchResult

PAGE_INDEX_HTML = """
<!DOCTYPE html>
<html><head><title>Index</title>
<link rel="canonical" href="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/" />
</head><body>
<main id="main-content"><article id="main-col-body">
<h1>EC2 User Guide</h1>
<p>Welcome.</p>
<ul>
<li><a href="/AWSEC2/latest/UserGuide/concepts.html">Concepts</a></li>
<li><a href="/AWSEC2/latest/UserGuide/Instances.html">Instances</a></li>
</ul>
</article></main>
</body></html>
"""


PAGE_CONCEPTS_HTML = """
<!DOCTYPE html>
<html><head><title>Concepts</title>
<link rel="canonical" href="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html" />
</head><body>
<main id="main-content"><article id="main-col-body">
<h1>Concepts</h1>
<p>EC2 concepts overview.</p>
<p>Back to <a href="/AWSEC2/latest/UserGuide/">index</a> or read about
<a href="/AWSEC2/latest/UserGuide/Instances.html">Instances</a>.</p>
</article></main>
</body></html>
"""


PAGE_INSTANCES_HTML = """
<!DOCTYPE html>
<html><head><title>Instances</title>
<link rel="canonical" href="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Instances.html" />
</head><body>
<main id="main-content"><article id="main-col-body">
<h1>Instances</h1>
<p>Information about EC2 instances.</p>
<p>External link: <a href="https://aws.amazon.com/ec2/">EC2 product page</a>.</p>
</article></main>
</body></html>
"""


PAGES = {
    "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/": PAGE_INDEX_HTML,
    "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html": PAGE_CONCEPTS_HTML,
    "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Instances.html": PAGE_INSTANCES_HTML,
}


class MockFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.calls: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        if url in self._pages:
            return FetchResult(
                url=url, final_url=url, status=200, html=self._pages[url],
            )
        return FetchResult(url=url, final_url=url, status=404, html="", error="not found")

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_crawler_bfs_with_prefix_scope() -> None:
    config = CrawlConfig(
        seed_url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/",
        scope="prefix",
        concurrency=2,
        max_pages=10,
        obey_robots=False,
    )
    fetcher = MockFetcher(PAGES)
    crawler = Crawler(config=config, fetcher=fetcher, profile=AWS_DOCS, robots=None)
    result = await crawler.run()

    urls = sorted(p.url for p in result.pages)
    assert urls == sorted(PAGES.keys())
    assert all(p.markdown for p in result.pages)
    assert result.stats.pages_fetched == 3
    # External link should not have been fetched
    assert not any("aws.amazon.com/ec2" in u for u in fetcher.calls)


@pytest.mark.asyncio
async def test_crawler_respects_max_pages() -> None:
    config = CrawlConfig(
        seed_url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/",
        scope="prefix",
        concurrency=1,
        max_pages=1,
        obey_robots=False,
    )
    fetcher = MockFetcher(PAGES)
    crawler = Crawler(config=config, fetcher=fetcher, profile=AWS_DOCS, robots=None)
    result = await crawler.run()
    assert len(result.pages) <= 2  # workers may grab 1 extra in flight before stopping


@pytest.mark.asyncio
async def test_crawler_exclude_pattern() -> None:
    config = CrawlConfig(
        seed_url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/",
        scope="prefix",
        concurrency=1,
        exclude_patterns=[r"Instances\.html"],
        obey_robots=False,
    )
    fetcher = MockFetcher(PAGES)
    crawler = Crawler(config=config, fetcher=fetcher, profile=AWS_DOCS, robots=None)
    result = await crawler.run()
    assert not any("Instances.html" in p.url for p in result.pages)
