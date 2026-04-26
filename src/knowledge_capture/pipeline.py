"""High-level orchestration: wire detector -> fetcher -> crawler -> writer."""

from __future__ import annotations

import logging

from knowledge_capture.cache import HttpCache
from knowledge_capture.config import CrawlConfig
from knowledge_capture.crawler import Crawler, ProgressCallback
from knowledge_capture.detector import (
    GENERIC_PROFILE,
    discover_sitemaps,
    match_known_profile,
)
from knowledge_capture.detector.heuristic import detect_profile as heuristic_detect
from knowledge_capture.detector.llm import propose_selectors
from knowledge_capture.detector.sitemap import fetch_sitemap_urls
from knowledge_capture.fetcher.browser import BrowserFetcher
from knowledge_capture.fetcher.http import HttpFetcher
from knowledge_capture.fetcher.hybrid import HybridFetcher
from knowledge_capture.models import CrawlResult, FetchResult, SiteProfile
from knowledge_capture.postprocess import (
    add_frontmatter,
    dedupe_pages,
    derive_site_name,
    normalize_headings,
    rewrite_links,
)
from knowledge_capture.robots import RobotsChecker
from knowledge_capture.writer import (
    write_bundle,
    write_index,
    write_llms_txt,
    write_manifest,
    write_pages,
)

log = logging.getLogger(__name__)


async def detect_site_profile(
    config: CrawlConfig,
    *,
    sample: FetchResult,
) -> SiteProfile:
    """Decide which :class:`SiteProfile` to use based on a sample HTML page."""

    known = match_known_profile(sample.html, sample.final_url or config.seed_url)
    if known is not None:
        log.info("Detected known profile: %s", known.name)
        return known

    heuristic = heuristic_detect(sample.html, sample.final_url or config.seed_url)
    if heuristic.confidence >= 0.55:
        log.info("Heuristic profile: %s (confidence=%.2f)",
                 heuristic.name, heuristic.confidence)
        return heuristic

    if config.use_llm_detection:
        log.info("Heuristic confidence low (%.2f); trying LLM", heuristic.confidence)
        llm = propose_selectors(sample.html, sample.final_url or config.seed_url)
        if llm is not None:
            return llm

    if heuristic.content_selector:
        return heuristic
    return GENERIC_PROFILE


def build_fetcher(
    config: CrawlConfig,
    *,
    cache: HttpCache | None,
) -> tuple[HybridFetcher | HttpFetcher, BrowserFetcher | None]:
    http = HttpFetcher(
        user_agent=config.user_agent,
        timeout=config.request_timeout,
        rate_limit_rps=config.rate_limit_rps,
        cache=cache,
    )

    if config.fetcher == "http":
        return http, None

    browser: BrowserFetcher | None = None
    force_browser = config.fetcher == "browser"
    if config.fetcher in {"auto", "browser"}:
        try:
            import playwright  # noqa: F401
        except ImportError as exc:
            if force_browser:
                raise RuntimeError(
                    "fetcher='browser' requires Playwright. "
                    "Install with `pip install knowledge-capture[browser]`."
                ) from exc
            log.info("Playwright not installed; falling back to HTTP-only mode.")
        else:
            browser = BrowserFetcher(
                user_agent=config.user_agent,
                timeout=config.request_timeout,
            )
    hybrid = HybridFetcher(http=http, browser=browser, force_browser=force_browser)
    return hybrid, browser


async def run_crawl(
    config: CrawlConfig,
    *,
    progress: ProgressCallback | None = None,
) -> CrawlResult:
    """Top-level orchestration: detect, crawl, post-process, write."""

    config.output_dir.mkdir(parents=True, exist_ok=True)
    cache = HttpCache(config.cache_dir)
    fetcher, _browser = build_fetcher(config, cache=cache)

    robots = RobotsChecker(config.seed_url, config.user_agent) if config.obey_robots else None
    if robots is not None:
        robots.load()

    try:
        sample = await fetcher.fetch(config.seed_url)
        if not sample.ok:
            raise RuntimeError(
                f"Could not fetch seed URL {config.seed_url}: status={sample.status} error={sample.error}"
            )

        profile = await detect_site_profile(config, sample=sample)

        sitemap_urls: list[str] = []
        candidates = discover_sitemaps(
            config.seed_url,
            robots_sitemaps=robots.sitemaps() if robots else None,
        )
        try:
            sitemap_urls = fetch_sitemap_urls(candidates, user_agent=config.user_agent)
        except Exception as exc:
            log.warning("Sitemap discovery failed: %s", exc)

        crawler = Crawler(
            config=config,
            fetcher=fetcher,
            profile=profile,
            robots=robots,
            seed_urls=sitemap_urls,
            progress=progress,
        )
        result = await crawler.run()
    finally:
        await fetcher.aclose()
        cache.close()

    kept, dropped = dedupe_pages(result.pages)
    result.pages = kept
    result.stats.duplicates_dropped = dropped

    site_name = derive_site_name(config.seed_url, override=config.site_title)
    url_to_path = {p.canonical_url: p.relative_path for p in result.pages if p.relative_path}

    for page in result.pages:
        rewritten = rewrite_links(page.markdown, page, url_to_path)
        page.markdown = normalize_headings(rewritten)

    write_pages(result.pages, config.output_dir, site_name=site_name)
    result.stats.pages_written = sum(1 for p in result.pages if p.relative_path)

    write_index(result.pages, config.output_dir / "index.md", site_title=site_name)
    if config.write_bundle:
        write_bundle(result.pages, config.output_dir / "bundle.md", site_title=site_name)
    if config.write_llms_txt:
        write_llms_txt(
            result.pages,
            config.output_dir / "llms.txt",
            site_title=site_name,
            description=f"Captured from {config.seed_url}",
        )
    if config.write_manifest:
        write_manifest(result, config.output_dir / "manifest.json")

    return result


async def inspect_url(url: str, *, use_llm: bool = False) -> dict[str, object]:
    """Fetch a single URL, detect its profile, and return a debug summary."""

    config = CrawlConfig(seed_url=url, use_llm_detection=use_llm)
    cache = HttpCache(config.cache_dir)
    fetcher, _browser = build_fetcher(config, cache=cache)
    try:
        sample = await fetcher.fetch(url)
        if not sample.ok:
            raise RuntimeError(
                f"Could not fetch {url}: status={sample.status} error={sample.error}"
            )
        profile = await detect_site_profile(config, sample=sample)

        from knowledge_capture.converter import html_to_markdown
        from knowledge_capture.extractor import extract_content
        from knowledge_capture.models import Page
        from knowledge_capture.utils import canonicalize_url, short_hash, url_to_relative_path

        extracted = extract_content(sample.html, sample.final_url, profile)
        markdown = html_to_markdown(extracted.content_html, base_url=sample.final_url)
        canonical = canonicalize_url(extracted.canonical_url or sample.final_url)

        page = Page(
            url=url,
            canonical_url=canonical,
            title=extracted.title,
            breadcrumbs=extracted.breadcrumbs,
            html=extracted.content_html,
            markdown=normalize_headings(markdown),
            outlinks=extracted.outlinks,
            fetcher_used="browser" if sample.js_used else "http",
            content_hash=short_hash(markdown),
            relative_path=url_to_relative_path(canonical),
        )
        full = add_frontmatter(page, site_name=derive_site_name(url))
        return {"profile": profile, "page": page, "markdown": full}
    finally:
        await fetcher.aclose()
        cache.close()
