"""The container only trusts forwarded headers from configured proxy addresses."""

import asyncio
import json
import re
import stat
import subprocess
from pathlib import Path

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def _cmd() -> list[str]:
    lines = [ln for ln in DOCKERFILE.read_text().splitlines() if ln.startswith("CMD ")]
    assert len(lines) == 1
    return json.loads(lines[0][4:])


def _run_cmd(tmp_path: Path, env_extra: dict[str, str]) -> list[str]:
    """Run the Dockerfile CMD with `bk` and `uvicorn` replaced by shims that print argv."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("bk", "uvicorn"):
        shim = bindir / name
        shim.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n')
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{bindir}:/usr/bin:/bin", **env_extra}
    out = subprocess.run(_cmd(), env=env, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def _allow_ips(argv: list[str]) -> str:
    [arg] = [a for a in argv if a.startswith("--forwarded-allow-ips")]
    return arg.split("=", 1)[1]


def test_dockerfile_never_trusts_every_peer():
    text = DOCKERFILE.read_text()
    assert not re.search(r"forwarded-allow-ips=['\"]?\*", text)
    assert "--proxy-headers" in " ".join(_cmd())


def test_default_trusted_proxy_is_localhost(tmp_path):
    argv = _run_cmd(tmp_path, {})
    assert _allow_ips(argv) == "127.0.0.1"


def test_trusted_proxy_comes_from_env(tmp_path):
    argv = _run_cmd(tmp_path, {"BK_FORWARDED_ALLOW_IPS": "172.18.0.1"})
    assert _allow_ips(argv) == "172.18.0.1"


def test_dockerfile_sets_default_env():
    assert "ENV BK_FORWARDED_ALLOW_IPS=127.0.0.1" in DOCKERFILE.read_text()


def test_env_example_documents_overwrite():
    env_example = DOCKERFILE.parent.parent / ".env.example"
    text = env_example.read_text()
    assert "BK_FORWARDED_ALLOW_IPS=127.0.0.1" in text
    assert "overwrite X-Forwarded-For" in text


def _client_seen(peer: str, xff: str) -> str:
    seen: dict[str, str] = {}

    async def app(scope, receive, send):
        seen["host"] = scope["client"][0]

    mw = ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")
    scope = {
        "type": "http",
        "client": (peer, 5000),
        "headers": [(b"x-forwarded-for", xff.encode())],
        "scheme": "http",
    }
    asyncio.run(mw(scope, None, None))
    return seen["host"]


def test_forged_header_from_untrusted_peer_is_ignored():
    assert _client_seen("203.0.113.9", "198.51.100.1") == "203.0.113.9"


def test_header_from_trusted_proxy_is_used():
    assert _client_seen("127.0.0.1", "198.51.100.1") == "198.51.100.1"
