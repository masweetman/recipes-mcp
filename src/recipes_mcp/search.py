from __future__ import annotations

import asyncio
import html
import itertools
import logging
import re
from dataclasses import asdict, dataclass
from urllib.parse import quote, urlsplit

import httpx

from .config import Blog, find_blog
from .fetch import Fetcher

log = logging.getLogger(__name__)

SEARXNG_BATCH = 5
CONCURRENCY = 8


@dataclass
class SearchResult:
    title: str
    url: str
    site: str
    snippet: str

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(text: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def normalize_url(url: str) -> str:
    p = urlsplit(url)
    host = (p.hostname or "").removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}".lower()


def parse_wordpress(items: list[dict], site: str) -> list[SearchResult]:
    return [
        SearchResult(
            title=_clean(i.get("title", {}).get("rendered")),
            url=i["link"],
            site=site,
            snippet=_clean(i.get("excerpt", {}).get("rendered"))[:300],
        )
        for i in items
        if i.get("link")
    ]


def parse_blogger(feed: dict, site: str) -> list[SearchResult]:
    results = []
    for e in feed.get("feed", {}).get("entry", []):
        link = next((x["href"] for x in e.get("link", []) if x.get("rel") == "alternate"), None)
        if not link:
            continue
        body = e.get("summary", {}).get("$t") or e.get("content", {}).get("$t")
        results.append(
            SearchResult(_clean(e.get("title", {}).get("$t")), link, site, _clean(body)[:300])
        )
    return results


def parse_searxng(data: dict, blogs: list[Blog]) -> list[SearchResult]:
    results = []
    for r in data.get("results", []):
        url = r.get("url", "")
        blog = find_blog(blogs, urlsplit(url).hostname or "")
        if blog:
            results.append(
                SearchResult(_clean(r.get("title")), url, blog.name, _clean(r.get("content"))[:300])
            )
    return results


def merge_results(per_site: list[list[SearchResult]], limit: int) -> list[SearchResult]:
    """Round-robin across sites so one blog can't dominate; drop duplicate URLs."""
    seen: set[str] = set()
    merged = []
    for group in itertools.zip_longest(*per_site):
        for r in group:
            if r is None:
                continue
            key = normalize_url(r.url)
            if key not in seen:
                seen.add(key)
                merged.append(r)
    return merged[:limit]


class Searcher:
    def __init__(self, fetcher: Fetcher, blogs: list[Blog], searxng_url: str):
        self.fetcher = fetcher
        self.blogs = blogs
        self.searxng_url = searxng_url.rstrip("/")
        self._searxng_client = httpx.AsyncClient(timeout=20)
        self._detected: dict[str, str] = {}
        self._sem = asyncio.Semaphore(CONCURRENCY)

    async def aclose(self) -> None:
        await self._searxng_client.aclose()

    async def _wordpress(self, blog: Blog, query: str, limit: int) -> list[SearchResult]:
        url = (
            f"https://{blog.domain}/wp-json/wp/v2/posts?search={quote(query)}"
            f"&per_page={limit}&_fields=title,link,excerpt"
        )
        return parse_wordpress(await self.fetcher.get_json(url), blog.name)

    async def _blogger(self, blog: Blog, query: str, limit: int) -> list[SearchResult]:
        url = (
            f"https://{blog.domain}/feeds/posts/default?q={quote(query)}"
            f"&alt=json&max-results={limit}"
        )
        return parse_blogger(await self.fetcher.get_json(url), blog.name)

    async def _searxng(self, blogs: list[Blog], query: str) -> list[list[SearchResult]]:
        async def one(batch: list[Blog]) -> list[SearchResult]:
            sites = " OR ".join(f"site:{b.domain}" for b in batch)
            async with self._sem:
                resp = await self._searxng_client.get(
                    f"{self.searxng_url}/search",
                    params={"q": f"({sites}) {query} recipe", "format": "json"},
                )
            resp.raise_for_status()
            return parse_searxng(resp.json(), self.blogs)

        batches = [blogs[i : i + SEARXNG_BATCH] for i in range(0, len(blogs), SEARXNG_BATCH)]
        out = await asyncio.gather(*(one(b) for b in batches), return_exceptions=True)
        groups = []
        for batch, res in zip(batches, out):
            if isinstance(res, Exception):
                log.warning("SearXNG batch failed (%s): %s", [b.domain for b in batch], res)
                continue
            # Split by site so round-robin merging stays fair within a batch.
            by_site: dict[str, list[SearchResult]] = {}
            for r in res:
                by_site.setdefault(r.site, []).append(r)
            groups.extend(by_site.values())
        return groups

    async def _resolve_mode(self, blog: Blog) -> str:
        if blog.search != "auto":
            return blog.search
        if blog.domain not in self._detected:
            try:
                data = await self.fetcher.get_json(
                    f"https://{blog.domain}/wp-json/wp/v2/posts?per_page=1&_fields=link"
                )
                ok = isinstance(data, list)
            except Exception:
                ok = False
            self._detected[blog.domain] = "wordpress" if ok else "searxng"
        return self._detected[blog.domain]

    async def _direct(self, blog: Blog, mode: str, query: str, limit: int) -> list[SearchResult]:
        async with self._sem:
            try:
                fn = self._wordpress if mode == "wordpress" else self._blogger
                return await fn(blog, query, limit)
            except Exception as e:
                log.warning("%s search failed for %s: %s", mode, blog.domain, e)
                return []

    async def search(self, query: str, sites: list[Blog], limit: int) -> list[SearchResult]:
        async def resolve(b: Blog) -> tuple[Blog, str]:
            async with self._sem:
                return b, await self._resolve_mode(b)

        modes = await asyncio.gather(*(resolve(b) for b in sites))
        direct = [(b, m) for b, m in modes if m != "searxng"]
        via_searxng = [b for b, m in modes if m == "searxng"]

        tasks = [self._direct(b, m, query, limit) for b, m in direct]
        groups = list(await asyncio.gather(*tasks))
        if via_searxng:
            groups.extend(await self._searxng(via_searxng, query))
        return merge_results([g for g in groups if g], limit)
