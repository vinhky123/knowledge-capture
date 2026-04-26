"""LLM-assisted selector proposal (optional, gated behind ``--use-llm``)."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from bs4 import BeautifulSoup

from knowledge_capture.models import SiteProfile

log = logging.getLogger(__name__)

_DOM_OUTLINE_LIMIT = 12_000
"""Max characters of DOM outline sent to the LLM."""

_PROMPT = """You are a documentation-site reverse-engineering assistant.

Given a trimmed DOM outline, return a JSON object with these keys:
- "content_selector": one CSS selector for the main article body
- "nav_selectors": list of CSS selectors for the side/global navigation
- "strip_selectors": list of CSS selectors that should be removed before extraction (headers, footers, breadcrumbs, feedback widgets, ads)

Reply with raw JSON only. No prose, no code fences.
"""


def _outline(html: str, limit: int = _DOM_OUTLINE_LIMIT) -> str:
    """Return a compact tree outline (tag + id + classes) for the LLM."""

    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    lines: list[str] = []

    def walk(node: Any, depth: int) -> None:
        if not getattr(node, "name", None):
            return
        if node.name in {"script", "style", "noscript"}:
            return
        attrs: list[str] = []
        if node.get("id"):
            attrs.append(f"#{node['id']}")
        cls = node.get("class") or []
        for c in cls[:3]:
            attrs.append(f".{c}")
        text = (node.get_text(" ", strip=True) or "")[:40]
        line = "  " * depth + node.name + "".join(attrs)
        if text:
            line += f"  // {text}"
        lines.append(line)
        if sum(len(line) for line in lines) > limit:
            return
        for child in getattr(node, "children", []):
            walk(child, depth + 1)

    walk(body, 0)
    return "\n".join(lines)[:limit]


def propose_selectors(html: str, url: str) -> SiteProfile | None:
    """Ask an LLM to propose selectors. Returns ``None`` if the LLM is unavailable."""

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY not set; skipping LLM detection")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        log.warning("openai package not installed; skipping LLM detection")
        return None

    outline = _outline(html)
    client = OpenAI(api_key=api_key)
    try:
        completion = client.chat.completions.create(
            model=os.environ.get("KCAP_LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": f"URL: {url}\n\nDOM OUTLINE:\n{outline}"},
            ],
            temperature=0,
        )
    except Exception as exc:
        log.warning("LLM call failed: %s", exc)
        return None

    raw = completion.choices[0].message.content or ""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON: %s", raw[:200])
        return None

    content = data.get("content_selector") or "main, article"
    return SiteProfile(
        name="llm",
        content_selector=content,
        nav_selectors=list(data.get("nav_selectors") or []),
        strip_selectors=list(data.get("strip_selectors") or []),
        confidence=0.7,
    )
