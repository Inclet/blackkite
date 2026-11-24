"""`bk digest-preview` and the committed web/public/digest/preview/ output."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from blackkite.cli import app as cli
from blackkite.delivery.digest import render_digest_preview
from blackkite.delivery.fixtures.digest_reference import REFERENCE
from blackkite.delivery.logo import kite_png

DIGEST_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "digest"
# Served by Vite preview for /digest/preview (the contract route, no trailing slash).
PREVIEW_HTML = DIGEST_DIR / "preview.html"
PREVIEW_LOGO = DIGEST_DIR / "preview" / "kite.png"
LOGO_SRC = "/digest/preview/kite.png"
needs_web = pytest.mark.skipif(not DIGEST_DIR.exists(), reason="web/ not next to api/")


@needs_web
def test_committed_preview_is_current():
    """web/public/digest/preview.html must equal a fresh `bk digest-preview` render."""
    assert PREVIEW_HTML.read_bytes() == render_digest_preview(REFERENCE, logo_src=LOGO_SRC).encode("utf-8"), (
        "regenerate: cd api && uv run bk digest-preview --fixture reference "
        "--out ../web/public/digest/preview.html --logo-src /digest/preview/kite.png "
        "--logo-out ../web/public/digest/preview/kite.png"
    )
    assert PREVIEW_LOGO.read_bytes() == kite_png()
    # Only the .html is served for the route; a directory index would be dead weight.
    assert not (DIGEST_DIR / "preview" / "index.html").exists()


def test_cli_writes_preview_and_logo(tmp_path):
    out = tmp_path / "p" / "index.html"
    r = CliRunner().invoke(cli, ["digest-preview", "--fixture", "reference", "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert out.read_text("utf-8") == render_digest_preview(REFERENCE, logo_src="kite.png")
    assert (out.parent / "kite.png").read_bytes() == kite_png()


def test_cli_rejects_unknown_fixture(tmp_path):
    r = CliRunner().invoke(cli, ["digest-preview", "--fixture", "nope", "--out", str(tmp_path / "x.html")])
    assert r.exit_code == 1


def test_cli_logo_options(tmp_path):
    out = tmp_path / "preview.html"
    logo = tmp_path / "preview" / "kite.png"
    r = CliRunner().invoke(cli, ["digest-preview", "--out", str(out),
                                 "--logo-src", LOGO_SRC, "--logo-out", str(logo)])
    assert r.exit_code == 0, r.output
    assert f'src="{LOGO_SRC}"' in out.read_text("utf-8")
    assert logo.read_bytes() == kite_png()
