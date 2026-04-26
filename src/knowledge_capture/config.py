"""Crawl configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from knowledge_capture import __version__

DEFAULT_USER_AGENT = (
    f"knowledge-capture/{__version__} (+https://github.com/your-org/knowledge-capture)"
)


class CrawlConfig(BaseModel):
    """Top-level configuration for a crawl run.

    All fields have safe defaults; only ``seed_url`` is required.
    """

    model_config = ConfigDict(extra="forbid")

    seed_url: str
    output_dir: Path = Field(default=Path("./out"))

    include_patterns: list[str] = Field(default_factory=list)
    """Regex patterns; URL must match at least one if list is non-empty."""

    exclude_patterns: list[str] = Field(default_factory=list)
    """Regex patterns; URL is dropped if any matches."""

    scope: Literal["prefix", "domain", "custom"] = "prefix"
    """How to constrain the crawl. ``custom`` defers entirely to include/exclude."""

    max_pages: int = 1000
    max_depth: int = 10
    concurrency: int = 8
    rate_limit_rps: float = 4.0
    """Per-host requests per second cap (token bucket)."""

    fetcher: Literal["auto", "http", "browser"] = "auto"
    """``auto`` = HTTP first with Playwright fallback when JS is needed."""

    use_llm_detection: bool = False
    obey_robots: bool = True
    cache_dir: Path = Field(default=Path("./.kcap-cache"))
    user_agent: str = DEFAULT_USER_AGENT
    request_timeout: float = 30.0
    """Per-request timeout in seconds."""

    write_bundle: bool = True
    write_llms_txt: bool = True
    write_manifest: bool = True

    site_title: str | None = None
    """Optional override for ``llms.txt`` and ``index.md``; auto-derived if absent."""

    @field_validator("seed_url")
    @classmethod
    def _validate_seed_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"seed_url must be an absolute http(s) URL, got {v!r}")
        return v

    @field_validator("max_pages", "max_depth", "concurrency")
    @classmethod
    def _positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be > 0")
        return v

    @field_validator("rate_limit_rps", "request_timeout")
    @classmethod
    def _positive_float(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("must be > 0")
        return v

    @property
    def base_host(self) -> str:
        return urlparse(self.seed_url).netloc

    @property
    def url_prefix(self) -> str:
        """Path prefix used for ``scope="prefix"``.

        Trims to the seed's directory so that a seed of
        ``/AWSEC2/latest/UserGuide/concepts.html`` yields
        ``/AWSEC2/latest/UserGuide/``.
        """
        parsed = urlparse(self.seed_url)
        path = parsed.path
        prefix = path if path.endswith("/") else path.rsplit("/", 1)[0] + "/"
        return f"{parsed.scheme}://{parsed.netloc}{prefix}"


def load_config(seed_url: str, **overrides: object) -> CrawlConfig:
    """Construct a :class:`CrawlConfig` from a seed URL and CLI overrides."""

    payload: dict[str, object] = {"seed_url": seed_url}
    payload.update({k: v for k, v in overrides.items() if v is not None})
    return CrawlConfig(**payload)  # type: ignore[arg-type]
