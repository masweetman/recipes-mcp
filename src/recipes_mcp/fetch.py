from __future__ import annotations

import json
from urllib.parse import urljoin

import httpx

from .config import Blog
from .security import UrlNotAllowed, validate_url

MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class Fetcher:
    def __init__(self, blogs: list[Blog], client: httpx.AsyncClient | None = None):
        self.blogs = blogs
        self.client = client or httpx.AsyncClient(
            timeout=15, headers=HEADERS, follow_redirects=False
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def get(self, url: str, accept: str = "text/html") -> tuple[str, str]:
        """GET an allowlisted URL, re-validating every redirect hop. Returns (final_url, body)."""
        for _ in range(MAX_REDIRECTS + 1):
            await validate_url(url, self.blogs)
            async with self.client.stream("GET", url, headers={"Accept": accept}) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise UrlNotAllowed("Redirect without Location header")
                    url = urljoin(url, location)
                    continue
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if accept.split("/")[-1] not in ctype:
                    raise ValueError(f"Unexpected content type: {ctype or 'unknown'}")
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise ValueError("Response too large")
                return url, body.decode(resp.encoding or "utf-8", errors="replace")
        raise UrlNotAllowed("Too many redirects")

    async def get_json(self, url: str):
        _, body = await self.get(url, accept="application/json")
        return json.loads(body)
