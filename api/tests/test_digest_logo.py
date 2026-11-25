"""Kite PNG for email: 2x, reproducible from the design SVG."""

import struct
from pathlib import Path

import pytest

from blackkite.delivery.logo import KITE_PNG, kite_png, render_kite_png

KITE_SVG = Path(__file__).resolve().parents[2] / "design" / "assets" / "kite-small.svg"


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_packaged_logo_is_2x_png():
    assert _png_size(kite_png()) == (84, 56)


@pytest.mark.skipif(not KITE_SVG.exists(), reason="design/ not next to api/")
def test_packaged_logo_matches_design_svg():
    assert KITE_PNG.read_bytes() == render_kite_png(KITE_SVG.read_text("utf-8"))
