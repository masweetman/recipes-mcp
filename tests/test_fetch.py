import httpx
import pytest
import respx

from recipes_mcp.config import Blog
from recipes_mcp.fetch import Fetcher
from recipes_mcp.security import UrlNotAllowed

from .test_security import resolve_to

BLOGS = [Blog(name="Example", domain="example.com")]


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    resolve_to(monkeypatch, "93.184.216.34")


@respx.mock
async def test_redirect_off_allowlist_is_blocked():
    respx.get("https://example.com/a").respond(302, headers={"location": "http://169.254.169.254/"})
    fetcher = Fetcher(BLOGS, httpx.AsyncClient())
    with pytest.raises(UrlNotAllowed):
        await fetcher.get("https://example.com/a")


@respx.mock
async def test_follows_allowed_redirect_and_returns_html():
    respx.get("https://example.com/a").respond(301, headers={"location": "/b"})
    respx.get("https://example.com/b").respond(200, text="<html>hi</html>", headers={"content-type": "text/html"})
    fetcher = Fetcher(BLOGS, httpx.AsyncClient())
    url, body = await fetcher.get("https://example.com/a")
    assert url == "https://example.com/b" and "hi" in body


@respx.mock
async def test_non_html_rejected():
    respx.get("https://example.com/a").respond(200, content=b"x", headers={"content-type": "application/pdf"})
    fetcher = Fetcher(BLOGS, httpx.AsyncClient())
    with pytest.raises(ValueError):
        await fetcher.get("https://example.com/a")
