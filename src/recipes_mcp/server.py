from __future__ import annotations

import logging

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from .config import Settings, find_blog, load_blogs
from .extract import get_recipe_data
from .fetch import Fetcher
from .search import Searcher
from .security import UrlNotAllowed

INSTRUCTIONS = (
    "Finds recipes on a curated list of food blogs. Typical flow: search_recipes, compare the "
    "top candidates with get_recipe, then import the chosen URL (or its extracted data) into "
    "the user's recipe manager."
)


def build_server(settings: Settings) -> FastMCP:
    blogs = load_blogs(settings.blogs_file)
    fetcher = Fetcher(blogs)
    searcher = Searcher(fetcher, blogs, settings.searxng_url)

    mcp = FastMCP(
        "recipes",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        streamable_http_path=f"/mcp/{settings.mcp_path_token}",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[settings.public_host, "localhost:*", "127.0.0.1:*"],
            allowed_origins=[f"https://{settings.public_host}"],
        ),
    )

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    @mcp.tool()
    async def list_sites() -> list[dict]:
        """List the food blogs that can be searched and fetched."""
        return [{"name": b.name, "domain": b.domain} for b in blogs]

    @mcp.tool()
    async def search_recipes(
        query: str, sites: list[str] | None = None, limit: int = 10
    ) -> list[dict]:
        """Search the configured food blogs for recipes matching a query.

        Args:
            query: What to look for, e.g. "chicken tikka masala".
            sites: Optional blog domains to restrict to (see list_sites). Defaults to all.
            limit: Maximum results, 1-25.

        Returns title, url, site and snippet per result. Use get_recipe on promising URLs.
        """
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        selected = blogs
        if sites:
            selected = [b for s in sites if (b := find_blog(blogs, s.lower().removeprefix("www."))) is not None]
            if not selected:
                raise ValueError("None of the given sites are configured; call list_sites")
        limit = max(1, min(limit, 25))
        results = await searcher.search(query, selected, limit)
        return [r.to_dict() for r in results]

    @mcp.tool()
    async def get_recipe(url: str) -> dict:
        """Fetch one recipe page and return structured data.

        Returns title, ingredients, instructions_list, total_time, yields, image, etc. If the page
        has no structured recipe data, structured is false and page_text holds the post text to
        read yourself. Only URLs on the configured blogs are allowed.
        """
        try:
            return await get_recipe_data(fetcher, url)
        except UrlNotAllowed as e:
            raise ValueError(str(e)) from None

    return mcp


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    logging.basicConfig(level=settings.log_level.upper())
    app = build_server(settings).streamable_http_app()
    # Access log is off because request paths contain the secret token.
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
    )


if __name__ == "__main__":
    main()
