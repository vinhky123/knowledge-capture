"""sitemap.xml discovery and parsing."""

from __future__ import annotations

import gzip
import io
import logging
from urllib.parse import urljoin, urlparse

import httpx
from lxml import etree

log = logging.getLogger(__name__)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def discover_sitemaps(base_url: str, *, robots_sitemaps: list[str] | None = None) -> list[str]:
    """Return candidate sitemap URLs in priority order."""

    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    candidates: list[str] = []
    for sm in robots_sitemaps or []:
        if sm not in candidates:
            candidates.append(sm)
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"):
        candidate = urljoin(root, path)
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def fetch_sitemap_urls(
    candidates: list[str],
    *,
    user_agent: str,
    timeout: float = 20.0,
    max_urls: int = 100_000,
) -> list[str]:
    """Fetch the first reachable sitemap and return all URLs it lists."""

    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": user_agent},
    ) as client:
        for url in candidates:
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                log.debug("Sitemap %s unreachable: %s", url, exc)
                continue
            if resp.status_code >= 400 or not resp.content:
                continue
            try:
                urls = list(parse_sitemap(url, resp.content, client=client, max_urls=max_urls))
            except Exception as exc:
                log.warning("Failed to parse sitemap %s: %s", url, exc)
                continue
            if urls:
                return urls
    return []


def parse_sitemap(
    url: str,
    content: bytes,
    *,
    client: httpx.Client | None = None,
    max_urls: int = 100_000,
    _depth: int = 0,
) -> list[str]:
    """Recursively parse a sitemap (handles ``sitemapindex`` of nested sitemaps)."""

    if _depth > 5:
        return []
    if url.endswith(".gz") or content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    try:
        root = etree.fromstring(content)
    except etree.XMLSyntaxError:
        try:
            root = etree.parse(io.BytesIO(content)).getroot()
        except Exception:
            return []

    tag = etree.QName(root.tag).localname
    urls: list[str] = []

    if tag == "sitemapindex":
        if client is None:
            return urls
        for loc in root.findall(".//sm:sitemap/sm:loc", _SITEMAP_NS):
            child_url = (loc.text or "").strip()
            if not child_url:
                continue
            try:
                child_resp = client.get(child_url)
            except httpx.HTTPError:
                continue
            if child_resp.status_code < 400 and child_resp.content:
                urls.extend(
                    parse_sitemap(
                        child_url, child_resp.content,
                        client=client, max_urls=max_urls, _depth=_depth + 1,
                    )
                )
            if len(urls) >= max_urls:
                return urls[:max_urls]
        return urls[:max_urls]

    if tag == "urlset":
        for loc in root.findall(".//sm:url/sm:loc", _SITEMAP_NS):
            text = (loc.text or "").strip()
            if text:
                urls.append(text)
                if len(urls) >= max_urls:
                    break
        return urls

    return urls
