"""Generic helpers shared across modules."""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import urldefrag, urlparse, urlunparse

_TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid$|gclid$|ref$|ref_|mc_|_hsenc$|_hsmi$)", re.IGNORECASE
)


def canonicalize_url(url: str) -> str:
    """Normalize a URL: drop fragment, sort/strip tracking params, lowercase host."""

    url, _ = urldefrag(url)
    parsed = urlparse(url)
    if not parsed.scheme:
        return url

    netloc = parsed.netloc.lower()

    if parsed.query:
        kept: list[str] = []
        for piece in parsed.query.split("&"):
            if not piece:
                continue
            key = piece.split("=", 1)[0]
            if _TRACKING_PARAMS.match(key):
                continue
            kept.append(piece)
        kept.sort()
        query = "&".join(kept)
    else:
        query = ""

    path = parsed.path or "/"
    if path != "/" and path.endswith("/index.html"):
        path = path[: -len("index.html")]

    return urlunparse((parsed.scheme, netloc, path, parsed.params, query, ""))


def url_to_relative_path(url: str) -> str:
    """Map a URL to a filesystem-friendly relative path with a ``.md`` suffix."""

    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"

    if path.endswith("/"):
        path = path + "index"
    else:
        p = PurePosixPath(path)
        if p.suffix in {".html", ".htm", ".xhtml", ".php", ".aspx"}:
            path = str(p.with_suffix(""))
        elif not p.suffix:
            pass

    if parsed.query:
        digest = hashlib.sha1(parsed.query.encode("utf-8")).hexdigest()[:8]
        path = f"{path}__{digest}"

    rel = f"{host}{path}.md"
    rel = rel.lstrip("/")
    rel = re.sub(r"[^A-Za-z0-9_./\-]", "_", rel)
    return rel


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_hash(text: str, n: int = 12) -> str:
    return stable_hash(text)[:n]
