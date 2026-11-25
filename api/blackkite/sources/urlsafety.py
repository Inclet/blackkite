"""Guard for admin-entered URLs (spec 10: source config is untrusted input).

Two checks, both required:

1. ``check_url`` / ``check_url_resolves``: before anything is fetched. http/https only,
   a host is required, no credentials in the URL, IP literals must be public, and
   every address the hostname resolves to must be public.
2. ``GuardedTransport``: at connect time. It resolves the host again, refuses if any
   address is not public, and connects to the address it just checked (the Host
   header and TLS SNI keep the real hostname, so certificates are still verified
   against it). A hostname that resolves to a public address for the first check
   and to an internal one a moment later (DNS rebinding) is refused at step 2, and
   the connection can only go to an address that passed the check.

Every redirect hop goes through the transport again, so redirects are re-validated.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from blackkite.collectors.base import CollectorError

Address = ipaddress.IPv4Address | ipaddress.IPv6Address
# host, port -> addresses. Defaults to the system resolver; tests inject their own.
Resolver = Callable[[str, int], list[str]]

ALLOWED_SCHEMES = ("http", "https")
MAX_URL_LENGTH = 2048

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class UnsafeURL(CollectorError):
    """A URL that must not be fetched (bad scheme, credentials, internal address)."""


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeURL(f"cannot resolve {host}: {e}") from None
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_address(ip: Address) -> bool:
    """True only for globally routable unicast addresses.

    IPv6 forms that embed an IPv4 address (mapped, NAT64, 6to4) are judged by the
    embedded address, so ::ffff:127.0.0.1 is not public.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_address(ip.ipv4_mapped)
        if ip in _NAT64:
            return is_public_address(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if ip.sixtofour is not None:
            return is_public_address(ip.sixtofour)
        if ip.teredo is not None:
            return all(is_public_address(a) for a in ip.teredo)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or not ip.is_global
    )


def _ip_literal(host: str) -> Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def check_url(url: str) -> tuple[str, str, int]:
    """Syntactic checks, no DNS. Returns (scheme, host, port). Raises UnsafeURL."""
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURL("empty URL")
    if len(url) > MAX_URL_LENGTH:
        raise UnsafeURL("URL too long")
    if any(c in url for c in "\r\n\t\x00 "):
        raise UnsafeURL("URL contains whitespace or control characters")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as e:
        raise UnsafeURL(f"malformed URL: {e}") from None
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURL("only http and https URLs are allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeURL("credentials in URLs are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURL("URL has no host")
    ip = _ip_literal(host)
    if ip is not None and not is_public_address(ip):
        raise UnsafeURL(f"address {ip} is not public")
    if ip is None and (host == "localhost" or host.endswith(".localhost")):
        raise UnsafeURL("localhost is not allowed")
    return scheme, host, port or (443 if scheme == "https" else 80)


def resolve_public(host: str, port: int, resolver: Resolver) -> list[Address]:
    """Resolve ``host`` and return its addresses; raise if ANY is not public."""
    literal = _ip_literal(host)
    raw = [str(literal)] if literal is not None else resolver(host, port)
    if not raw:
        raise UnsafeURL(f"{host} did not resolve")
    addresses: list[Address] = []
    for a in raw:
        try:
            ip = ipaddress.ip_address(a.split("%", 1)[0])
        except ValueError:
            raise UnsafeURL(f"{host} resolved to an invalid address") from None
        if not is_public_address(ip):
            raise UnsafeURL(f"{host} resolves to a non-public address ({ip})")
        addresses.append(ip)
    return addresses


def check_url_resolves(url: str, resolver: Resolver = system_resolver) -> str:
    """Full pre-fetch check: syntax plus every resolved address public."""
    _, host, port = check_url(url)
    resolve_public(host, port, resolver)
    return url


class GuardedTransport(httpx.BaseTransport):
    """Validates every request at connect time and pins it to a checked address.

    ``inner`` does the actual I/O. In production it is an ``httpx.HTTPTransport``
    (env proxies off); tests pass an ``httpx.MockTransport``, which then sees the
    pinned IP in the URL and the real hostname in the Host header.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport | None = None,
        resolver: Resolver = system_resolver,
    ) -> None:
        self.inner = inner or httpx.HTTPTransport(retries=0)
        self.resolver = resolver

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        scheme, host, port = check_url(url)
        address = resolve_public(host, port, self.resolver)[0]
        if _ip_literal(host) is None:
            ip_host = str(address)
            request.url = request.url.copy_with(host=ip_host)
            request.extensions = {**request.extensions, "sni_hostname": host}
            # httpx already set Host from the original URL; keep it explicit.
            default_port = 443 if scheme == "https" else 80
            request.headers["Host"] = host if port == default_port else f"{host}:{port}"
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()
