"""Convert cleaned HTML fragments into AI-friendly Markdown."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag
from markdownify import ATX, MarkdownConverter

_LANGUAGE_CLASS_RE = re.compile(r"language-([\w+\-]+)")
_HIGHLIGHT_CLASS_RE = re.compile(r"highlight-([\w+\-]+)")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


class _DocsMarkdownConverter(MarkdownConverter):
    """Custom markdownify converter with stronger code-fence handling."""

    def convert_pre(self, el: Tag, text: str, parent_tags: Any | None = None) -> str:
        language = self._detect_language(el)
        code = el.get_text("\n")
        code = _dedent(code).rstrip("\n")
        fence = "```"
        return f"\n\n{fence}{language}\n{code}\n{fence}\n\n"

    def convert_code(self, el: Tag, text: str, parent_tags: Any | None = None) -> str:
        parents: list[Tag] = []
        for parent in el.parents:
            if isinstance(parent, Tag):
                parents.append(parent)
        if any(p.name == "pre" for p in parents):
            return text
        return f"`{text}`" if text else ""

    @staticmethod
    def _detect_language(el: Tag) -> str:
        candidates: list[str] = []
        for node in [el, *el.find_all(True, recursive=True)]:
            if not isinstance(node, Tag):
                continue
            classes = node.get("class") or []
            for cls in classes:
                m = _LANGUAGE_CLASS_RE.match(cls)
                if m:
                    candidates.append(m.group(1))
                m = _HIGHLIGHT_CLASS_RE.match(cls)
                if m:
                    candidates.append(m.group(1))
            data_lang = node.get("data-lang") or node.get("data-language")
            if data_lang:
                candidates.append(str(data_lang))
        for c in candidates:
            return c.lower()
        return ""


def _dedent(text: str) -> str:
    lines = text.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return text
    indent = min(len(ln) - len(ln.lstrip(" ")) for ln in non_empty)
    if indent == 0:
        return text
    return "\n".join(ln[indent:] if len(ln) >= indent else ln for ln in lines)


def html_to_markdown(html: str, base_url: str | None = None) -> str:
    """Convert an HTML fragment to Markdown.

    ``base_url`` is currently informational; link rewriting is handled in
    :mod:`knowledge_capture.postprocess`.
    """

    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    converter = _DocsMarkdownConverter(
        heading_style=ATX,
        bullets="-",
        strip=["script", "style"],
        code_language="",
        escape_underscores=False,
        escape_asterisks=False,
    )
    md = converter.convert_soup(soup)
    md = _BLANK_LINES_RE.sub("\n\n", md).strip()
    return md + "\n"
