from __future__ import annotations

import html as htmllib
import re
from html.parser import HTMLParser

from recipe_scrapers import scrape_html

from .fetch import Fetcher

_FIELDS = [
    "title",
    "description",
    "image",
    "total_time",
    "prep_time",
    "cook_time",
    "yields",
    "ingredients",
    "instructions_list",
    "cuisine",
    "category",
    "ratings",
    "ratings_count",
]

_VOID = {"br", "img", "hr", "meta", "link", "input", "source", "wbr"}
_SKIP = {"script", "style", "noscript", "svg"}
_PAGE_TEXT_LIMIT = 8000
_NO_RECIPE = "No recipe found on page (it may be paywalled or not a recipe)"


class _TextExtractor(HTMLParser):
    """Collects text inside the first element matching `want`; ignores script/style."""

    def __init__(self, want):
        super().__init__()
        self.want = want
        self.depth = 0
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if self.depth and tag == "br":
                self.parts.append("\n")
            return
        if self.depth:
            self.depth += 1
            self.parts.append("\n")
        elif not self.parts and self.want(tag, dict(attrs)):
            self.depth = 1
        if self.depth and tag in _SKIP:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in _VOID or not self.depth:
            return
        if tag in _SKIP and self.skip:
            self.skip -= 1
        self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.parts.append(data)


def page_text(html: str) -> str:
    """Readable post text, for sites that publish recipes as prose without schema.org data."""
    matchers = (
        lambda t, a: "post-body" in (a.get("class") or ""),
        lambda t, a: t == "article",
        lambda t, a: t == "body",
    )
    for want in matchers:
        parser = _TextExtractor(want)
        parser.feed(html)
        text = re.sub(r"\s*\n\s*", "\n", "".join(parser.parts)).strip()
        if text:
            return text[:_PAGE_TEXT_LIMIT]
    return ""


def extract_recipe(html: str, url: str) -> dict:
    try:
        scraper = scrape_html(html, org_url=url, supported_only=False)
    except Exception:
        text = page_text(html)
        if not text:
            raise ValueError(_NO_RECIPE) from None
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        return {
            "url": url,
            "structured": False,
            "title": htmllib.unescape(re.sub(r"\s+", " ", title.group(1))).strip() if title else None,
            "page_text": text,
        }

    recipe: dict = {"url": url, "structured": True}
    for field in _FIELDS:
        try:
            recipe[field] = getattr(scraper, field)()
        except Exception:
            recipe[field] = None
    if not recipe["ingredients"] and not recipe["instructions_list"]:
        raise ValueError(_NO_RECIPE)
    return recipe


async def get_recipe_data(fetcher: Fetcher, url: str) -> dict:
    final_url, html = await fetcher.get(url)
    return extract_recipe(html, final_url)
