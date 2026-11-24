"""The kite mark as a PNG for email (decision 7: no SVG in mail).

Email clients do not render SVG, so the digest shows the small kite as a PNG. The
board draws `design/assets/kite-small.svg` at 42 x 28 CSS px, rotated -16deg
about its centre, in #2B2A28. `render_kite_png` reproduces exactly that box at
`scale` (2x by default, for sharp high-density screens) with a transparent
background, so the email can show it with <img width="42" height="28">.

A small scanline rasteriser does the drawing so the result is reproducible
without a browser or native libraries. It understands the subset of SVG the kite
uses: one <path> with absolute M, L, C and Z commands, a fill colour and a viewBox.

The packaged copy lives at blackkite/delivery/assets/kite.png (the API image does
not ship design/); a test checks it still equals a fresh render of the design file.
"""

from __future__ import annotations

import math
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
KITE_PNG = ASSETS / "kite.png"

# The board's placement of the mark (design/reference/digest-email.html, line 21).
BOX_W, BOX_H = 42, 28
ROTATE_DEG = -16.0
SCALE = 2
SUBSAMPLES = 16  # sub-scanlines per pixel row; horizontal coverage is exact
CURVE_STEPS = 48

Point = tuple[float, float]


def _parse_svg(svg: str) -> tuple[tuple[float, float, float, float], str, str]:
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    paths = root.findall(f"{ns}path") or root.findall("path")
    if len(paths) != 1:
        raise ValueError("expected exactly one <path>")
    vb = tuple(float(v) for v in root.attrib["viewBox"].replace(",", " ").split())
    return vb, paths[0].attrib["d"], paths[0].attrib.get("fill", "#000000")  # type: ignore[return-value]


def _flatten(d: str) -> list[list[Point]]:
    tokens = re.findall(r"[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?", d)
    polys: list[list[Point]] = []
    cur: Point = (0.0, 0.0)
    start: Point = cur
    i = 0

    def num(k: int) -> float:
        return float(tokens[i + k])

    while i < len(tokens):
        cmd = tokens[i]
        if cmd == "M":
            cur = start = (num(1), num(2))
            polys.append([cur])
            i += 3
        elif cmd == "L":
            cur = (num(1), num(2))
            polys[-1].append(cur)
            i += 3
        elif cmd == "C":
            p0, p1, p2, p3 = cur, (num(1), num(2)), (num(3), num(4)), (num(5), num(6))
            for s in range(1, CURVE_STEPS + 1):
                t = s / CURVE_STEPS
                u = 1 - t
                polys[-1].append((
                    u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
                ))
            cur = p3
            i += 7
        elif cmd in "Zz":
            polys[-1].append(start)
            cur = start
            i += 1
        else:
            raise ValueError(f"unsupported path command {cmd!r}")
    return polys


def _png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def render_kite_png(svg: str, scale: int = SCALE) -> bytes:
    """Render the kite SVG as the board places it, at `scale` x, as PNG bytes."""
    (vx, vy, vw, vh), d, fill = _parse_svg(svg)
    w, h = BOX_W * scale, BOX_H * scale
    # viewBox -> CSS box (preserveAspectRatio xMidYMid meet), then rotate about the
    # box centre (CSS transform-origin 50% 50%), then scale to device pixels.
    k = min(BOX_W / vw, BOX_H / vh)
    ox, oy = (BOX_W - vw * k) / 2, (BOX_H - vh * k) / 2
    a = math.radians(ROTATE_DEG)
    ca, sa = math.cos(a), math.sin(a)
    cx, cy = BOX_W / 2, BOX_H / 2

    def place(p: Point) -> Point:
        x = (p[0] - vx) * k + ox - cx
        y = (p[1] - vy) * k + oy - cy
        return ((x * ca - y * sa + cx) * scale, (x * sa + y * ca + cy) * scale)

    edges: list[tuple[float, float, float, float]] = []
    for poly in _flatten(d):
        pts = [place(p) for p in poly]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
            if y0 != y1:
                edges.append((x0, y0, x1, y1))

    cover = [0.0] * (w * h)
    for sy in range(h * SUBSAMPLES):
        y = (sy + 0.5) / SUBSAMPLES
        row = sy // SUBSAMPLES
        xs: list[tuple[float, int]] = []
        for x0, y0, x1, y1 in edges:
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append((x0 + (y - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1))
        xs.sort()
        winding = 0
        for j in range(len(xs) - 1):
            (xa, dw), (xb, _) = xs[j], xs[j + 1]
            winding += dw
            if winding == 0 or xb <= xa:
                continue
            lo, hi = max(xa, 0.0), min(xb, float(w))
            px = int(lo)
            while px < hi and px < w:
                overlap = min(hi, px + 1) - max(lo, px)
                if overlap > 0:
                    cover[row * w + px] += overlap / SUBSAMPLES
                px += 1

    r, g, b = (int(fill.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    out = bytearray()
    for c in cover:
        out += bytes((r, g, b, max(0, min(255, round(c * 255)))))
    return _png(w, h, bytes(out))


def kite_png() -> bytes:
    """The packaged kite PNG (84 x 56 px, shown at 42 x 28)."""
    return KITE_PNG.read_bytes()
