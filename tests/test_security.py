import socket

import pytest

from recipes_mcp.config import Blog
from recipes_mcp.security import UrlNotAllowed, validate_url

BLOGS = [Blog(name="Example", domain="example.com")]


def resolve_to(monkeypatch, ip: str):
    def fake(host, port, *args, **kwargs):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    resolve_to(monkeypatch, "93.184.216.34")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https://user:pw@example.com/x",
        "https://example.com:8080/x",
        "https://evil.com/x",
        "https://example.com.evil.com/x",
        "http://127.0.0.1/x",
        "http://[::1]/x",
        "http://169.254.169.254/latest/meta-data",
    ],
)
async def test_rejected(url):
    with pytest.raises(UrlNotAllowed):
        await validate_url(url, BLOGS)


@pytest.mark.parametrize(
    "url", ["https://example.com/a", "http://www.example.com/a", "https://sub.example.com/a"]
)
async def test_allowed(url):
    assert await validate_url(url, BLOGS)


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.1.1", "::1", "::ffff:10.0.0.1", "fe80::1"]
)
async def test_private_resolution_rejected(monkeypatch, ip):
    resolve_to(monkeypatch, ip)
    with pytest.raises(UrlNotAllowed):
        await validate_url("https://example.com/a", BLOGS)
