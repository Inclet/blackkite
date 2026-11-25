"""URL guard for untrusted source config (spec 10). No network: resolvers are fakes."""

import ipaddress

import httpx
import pytest

from blackkite.sources.urlsafety import (
    GuardedTransport,
    UnsafeURL,
    check_url,
    check_url_resolves,
    is_public_address,
)

PUBLIC = "93.184.215.14"


def fixed(*addrs: str):
    def resolve(host: str, port: int) -> list[str]:
        return list(addrs)

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/list",
        "http://example.org:8080/a?b=1",
        f"https://{PUBLIC}/",
        "https://[2606:4700::1111]/",
    ],
)
def test_accepts_public_http_urls(url):
    check_url(url)


@pytest.mark.parametrize(
    ("url", "why"),
    [
        ("ftp://example.org/", "only http"),
        ("file:///etc/passwd", "only http"),
        ("javascript:alert(1)", "only http"),
        ("https://user:pw@example.org/", "credentials"),
        ("https://user@example.org/", "credentials"),
        ("https:///nohost", "no host"),
        ("https://127.0.0.1/", "not public"),
        ("https://10.1.2.3/", "not public"),
        ("https://172.16.0.1/", "not public"),
        ("https://192.168.1.1/", "not public"),
        ("https://169.254.169.254/latest/meta-data", "not public"),
        ("https://100.64.0.1/", "not public"),
        ("https://0.0.0.0/", "not public"),
        ("https://240.0.0.1/", "not public"),
        ("https://[::1]/", "not public"),
        ("https://[fe80::1]/", "not public"),
        ("https://[fc00::1]/", "not public"),
        ("https://[::ffff:127.0.0.1]/", "not public"),
        ("https://localhost/", "localhost"),
        ("https://a.localhost/", "localhost"),
        ("https://example.org/a b", "whitespace"),
        ("https://example.org:99999/", "malformed"),
        ("", "empty"),
    ],
)
def test_rejects_unsafe_urls(url, why):
    with pytest.raises(UnsafeURL, match=why):
        check_url(url)


@pytest.mark.parametrize(
    "ip",
    ["::ffff:10.0.0.1", "64:ff9b::7f00:1", "2002:7f00:1::", "224.0.0.1", "192.0.2.1"],
)
def test_embedded_and_special_ipv6_ipv4_not_public(ip):
    assert not is_public_address(ipaddress.ip_address(ip))


def test_resolved_hostname_any_private_address_refused():
    check_url_resolves("https://example.org/", fixed(PUBLIC))
    with pytest.raises(UnsafeURL, match="non-public"):
        check_url_resolves("https://example.org/", fixed(PUBLIC, "10.0.0.5"))
    # Decimal/short IPv4 forms are not IP literals to Python, so they get resolved;
    # whatever the resolver turns them into is checked.
    with pytest.raises(UnsafeURL, match="non-public"):
        check_url_resolves("http://2130706433/", fixed("127.0.0.1"))


def test_transport_pins_connection_to_checked_address():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok")

    t = GuardedTransport(httpx.MockTransport(handler), resolver=fixed(PUBLIC))
    with httpx.Client(transport=t) as c:
        r = c.get("https://example.org/x?y=1")
    assert r.text == "ok"
    req = seen[0]
    assert req.url.host == PUBLIC
    assert req.url.path == "/x" and req.url.query == b"y=1"
    assert req.headers["host"] == "example.org"
    assert req.extensions["sni_hostname"] == "example.org"


def test_transport_rechecks_at_connect_time_dns_rebinding():
    """First lookup (pre-check) public, second (connect) private: refused, no request."""
    answers = iter([[PUBLIC], ["127.0.0.1"]])
    calls = []

    def rebinding(host, port):
        return next(answers)

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    check_url_resolves("https://rebind.example/", rebinding)
    t = GuardedTransport(httpx.MockTransport(handler), resolver=rebinding)
    with httpx.Client(transport=t) as c, pytest.raises(UnsafeURL):
        c.get("https://rebind.example/")
    assert calls == []


def test_transport_blocks_redirect_to_internal_address():
    def resolve(host, port):
        return {"example.org": [PUBLIC], "internal.example": ["192.168.0.10"]}[host]

    def handler(request):
        if request.headers["host"] == "example.org":
            return httpx.Response(302, headers={"Location": "http://internal.example/"})
        raise AssertionError("internal host must not be reached")

    t = GuardedTransport(httpx.MockTransport(handler), resolver=resolve)
    with (
        httpx.Client(transport=t, follow_redirects=True) as c,
        pytest.raises(UnsafeURL),
    ):
        c.get("https://example.org/")
