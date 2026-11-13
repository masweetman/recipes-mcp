from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from .config import Blog, find_blog


class UrlNotAllowed(ValueError):
    pass


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def validate_url(url: str, blogs: list[Blog]) -> str:
    """Return the host if the URL is safe to fetch, else raise UrlNotAllowed."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UrlNotAllowed("Only http(s) URLs are allowed")
    if parts.username or parts.password:
        raise UrlNotAllowed("URLs with credentials are not allowed")
    host = parts.hostname
    if not host:
        raise UrlNotAllowed("URL has no host")
    try:
        port = parts.port
    except ValueError:
        raise UrlNotAllowed("Invalid port") from None
    if port not in (None, 80, 443):
        raise UrlNotAllowed("Only default ports are allowed")
    if find_blog(blogs, host) is None:
        raise UrlNotAllowed(f"{host} is not in the configured blog list")

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UrlNotAllowed(f"Could not resolve {host}") from None
    for info in infos:
        if not _is_public(ipaddress.ip_address(info[4][0])):
            raise UrlNotAllowed(f"{host} resolves to a non-public address")
    return host
