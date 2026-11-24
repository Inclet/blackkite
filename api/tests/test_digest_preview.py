"""`bk digest-preview` and the committed web/public/digest/preview/ output."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from blackkite.cli import app as cli
from blackkite.delivery.digest import render_digest_preview
from blackkite.delivery.fixtures.digest_reference import REFERENCE
from blackkite.delivery.logo import kite_png

PREVIEW_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "digest" / "preview"
needs_web = pytest.mark.skipif(not PREVIEW_DIR.exists(), reason="web/ not next to api/")


@needs_web
def test_committed_preview_is_current():
    """web/public/digest/preview/ must equal a fresh `bk digest-preview --fixture reference`."""
    committed = (PREVIEW_DIR / "index.html").read_bytes()
    assert committed == render_digest_preview(REFERENCE, logo_src="kite.png").encode("utf-8"), (
        "regenerate: cd api && uv run bk digest-preview --fixture reference "
        "--out ../web/public/digest/preview/index.html"
    )
    assert (PREVIEW_DIR / "kite.png").read_bytes() == kite_png()


def test_cli_writes_preview_and_logo(tmp_path):
    out = tmp_path / "p" / "index.html"
    r = CliRunner().invoke(cli, ["digest-preview", "--fixture", "reference", "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert out.read_text("utf-8") == render_digest_preview(REFERENCE, logo_src="kite.png")
    assert (out.parent / "kite.png").read_bytes() == kite_png()


def test_cli_rejects_unknown_fixture(tmp_path):
    r = CliRunner().invoke(cli, ["digest-preview", "--fixture", "nope", "--out", str(tmp_path / "x.html")])
    assert r.exit_code == 1
